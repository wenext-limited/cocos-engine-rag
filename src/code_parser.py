"""
Source code parser for Cocos Creator engine using tree-sitter.

Parses TypeScript and C++ source files into structured chunks suitable for RAG indexing.
Each chunk represents a semantically meaningful code unit (class summary, method, enum, etc.)
with rich metadata and a natural-language embedding text derived from JSDoc/Doxygen comments.
"""

import os
import re
import json
import hashlib
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

import tree_sitter_typescript as ts_typescript
import tree_sitter_cpp as ts_cpp
from tree_sitter import Language, Parser

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize tree-sitter languages
TS_LANGUAGE = Language(ts_typescript.language_typescript())
CPP_LANGUAGE = Language(ts_cpp.language())

# GitHub base URL for source links
GITHUB_BASE = "https://github.com/cocos/cocos-engine/blob"

# Per-file safety limits (circuit breakers).
# These guard against pathological AST traversals or accidental duplication bugs
# from eating all memory / pegging CPU. If a file hits these limits we log and
# abort parsing that single file.
MAX_NODES_PER_FILE = 500_000
MAX_CHUNKS_PER_FILE = 5_000


class ParserBudgetExceeded(Exception):
    """Raised when a single file exceeds traversal/chunk budget."""


# ---------------------------------------------------------------------------
# JSDoc / Doxygen comment extraction
# ---------------------------------------------------------------------------


def extract_jsdoc_parts(comment_text: str) -> Dict[str, str]:
    """Extract structured parts from a JSDoc/Doxygen comment block."""
    result = {
        "description_en": "",
        "description_zh": "",
        "params": [],
        "returns": "",
        "examples": [],
        "deprecated": "",
        "is_internal": False,
        "is_engine_internal": False,
        "raw": comment_text,
    }

    if not comment_text:
        return result

    # Clean comment markers
    text = comment_text.strip()
    text = re.sub(r"^/\*\*?", "", text)
    text = re.sub(r"\*/$", "", text)
    lines = []
    for line in text.split("\n"):
        line = re.sub(r"^\s*\*\s?", "", line)
        lines.append(line)
    text = "\n".join(lines).strip()

    # Check for @internal / @engineInternal
    if "@internal" in text:
        result["is_internal"] = True
    if "@engineInternal" in text:
        result["is_engine_internal"] = True

    # Extract @en blocks
    en_match = re.search(
        r"@en\s*\n?(.*?)(?=@zh|@param|@returns?|@example|@deprecated|@default|@readonly|@internal|@engineInternal|$)",
        text,
        re.DOTALL,
    )
    if en_match:
        result["description_en"] = en_match.group(1).strip()

    # Extract @zh blocks
    zh_match = re.search(
        r"@zh\s*\n?(.*?)(?=@en|@param|@returns?|@example|@deprecated|@default|@readonly|@internal|@engineInternal|$)",
        text,
        re.DOTALL,
    )
    if zh_match:
        result["description_zh"] = zh_match.group(1).strip()

    # If no @en/@zh tags, the whole text is the description
    if not result["description_en"] and not result["description_zh"]:
        # Try to extract before any @ tag
        plain = re.split(r"\n\s*@", text, maxsplit=1)[0].strip()
        if plain:
            result["description_en"] = plain

    # Extract @param
    for m in re.finditer(
        r"@param\s+(?:\{[^}]*\}\s+)?(\w+)\s+(.*?)(?=@param|@returns?|@example|@deprecated|$)",
        text,
        re.DOTALL,
    ):
        result["params"].append({"name": m.group(1), "desc": m.group(2).strip()})

    # Extract @returns
    ret_match = re.search(
        r"@returns?\s+(.*?)(?=@param|@example|@deprecated|$)", text, re.DOTALL
    )
    if ret_match:
        result["returns"] = ret_match.group(1).strip()

    # Extract @example
    for m in re.finditer(r"@example\s*\n?(.*?)(?=@\w|$)", text, re.DOTALL):
        example = m.group(1).strip()
        if example:
            result["examples"].append(example)

    # Extract @deprecated
    dep_match = re.search(r"@deprecated\s+(.*?)(?=@|$)", text, re.DOTALL)
    if dep_match:
        result["deprecated"] = dep_match.group(1).strip()

    return result


# ---------------------------------------------------------------------------
# Tree-sitter TypeScript parser
# ---------------------------------------------------------------------------


class TypeScriptCodeParser:
    """Parses TypeScript source files into structured code chunks."""

    def __init__(self):
        self.parser = Parser(TS_LANGUAGE)

    def parse_file(
        self, file_path: str, version: str, base_dir: str
    ) -> List[Dict[str, Any]]:
        """Parse a single TypeScript file into code chunks."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()
        except Exception as e:
            logger.warning(f"Failed to read {file_path}: {e}")
            return []

        if not source.strip():
            return []

        rel_path = os.path.relpath(file_path, base_dir).replace("\\", "/")
        module_path = rel_path.replace("/", ".").replace(".ts", "")

        source_bytes = source.encode("utf-8")
        tree = self.parser.parse(source_bytes)
        root = tree.root_node

        chunks: List[Dict[str, Any]] = []
        state = {"nodes_visited": 0}
        ctx = {
            "file_path": rel_path,
            "module_path": module_path,
            "version": version,
            "language": "typescript",
        }

        try:
            self._walk(root, source_bytes, chunks, ctx, state)
        except ParserBudgetExceeded as e:
            logger.warning(f"Parser budget exceeded for {rel_path}: {e}")
            # Keep whatever we collected so far; better than nothing.

        # If no structured chunks extracted (small utility file), treat as whole file
        if not chunks and len(source) < 4000:
            chunks.append(self._make_file_chunk(source, rel_path, module_path, version))

        return chunks

    # Nodes that are "terminals" for our extraction: once we extract one we do
    # NOT descend into it again (otherwise we'd emit nested methods recursively
    # or duplicate chunks).
    _TERMINAL_TYPES = (
        "class_declaration",
        "abstract_class_declaration",
        "enum_declaration",
        "interface_declaration",
        "type_alias_declaration",
        "function_declaration",
        "lexical_declaration",
    )

    def _walk(self, node, source_bytes: bytes, chunks: list, ctx: dict, state: dict):
        """Recursively walk the AST.

        Uses explicit recursion (bounded by AST depth, which in practice is
        well under Python's recursion limit for real source files). This avoids
        the subtle cursor state-machine bugs that produced an infinite loop
        in the previous implementation.
        """
        # Circuit breakers: abort this file if something goes pathological.
        state["nodes_visited"] += 1
        if state["nodes_visited"] > MAX_NODES_PER_FILE:
            raise ParserBudgetExceeded(f"visited > {MAX_NODES_PER_FILE} nodes")
        if len(chunks) > MAX_CHUNKS_PER_FILE:
            raise ParserBudgetExceeded(f"emitted > {MAX_CHUNKS_PER_FILE} chunks")

        t = node.type

        if t in ("class_declaration", "abstract_class_declaration"):
            self._extract_class(node, source_bytes, chunks, ctx)
            return  # do not descend: methods are emitted inside _extract_class
        if t == "enum_declaration":
            self._extract_enum(node, source_bytes, chunks, ctx)
            return
        if t in ("function_declaration", "lexical_declaration"):
            self._extract_top_level_function(node, source_bytes, chunks, ctx)
            return
        if t in ("interface_declaration", "type_alias_declaration"):
            self._extract_type_declaration(node, source_bytes, chunks, ctx)
            return

        if t == "export_statement":
            # Descend exactly one level into the export statement so we hit the
            # underlying class/enum/function declaration. Anything else inside
            # the export (identifiers, punctuation) is ignored by the recursion.
            for child in node.named_children:
                self._walk(child, source_bytes, chunks, ctx, state)
            return

        # Generic descent for program / statement_block / namespace / etc.
        for child in node.named_children:
            self._walk(child, source_bytes, chunks, ctx, state)

    def _get_preceding_comment(self, node, source_bytes: bytes) -> str:
        """Get the JSDoc comment immediately preceding a node."""
        prev = node.prev_named_sibling
        if prev and prev.type == "comment":
            text = source_bytes[prev.start_byte : prev.end_byte].decode(
                "utf-8", errors="replace"
            )
            if text.strip().startswith("/**"):
                return text
        # Check for two consecutive comments (common in Cocos: @zh block + @en block)
        if prev and prev.type == "comment":
            prev2 = prev.prev_named_sibling
            if prev2 and prev2.type == "comment":
                text2 = source_bytes[prev2.start_byte : prev2.end_byte].decode(
                    "utf-8", errors="replace"
                )
                text1 = source_bytes[prev.start_byte : prev.end_byte].decode(
                    "utf-8", errors="replace"
                )
                if text2.strip().startswith("/**") or text1.strip().startswith("/**"):
                    return text2 + "\n" + text1
        return ""

    def _extract_class(self, node, source_bytes: bytes, chunks: list, ctx: dict):
        """Extract a class: one summary chunk + one chunk per method."""
        # Get class name
        class_name = ""
        parent_classes = []
        decorators = []

        for child in node.children:
            if child.type == "type_identifier":
                class_name = source_bytes[child.start_byte : child.end_byte].decode(
                    "utf-8"
                )
            elif child.type == "class_heritage":
                heritage_text = source_bytes[child.start_byte : child.end_byte].decode(
                    "utf-8"
                )
                extends_match = re.search(r"extends\s+(\w+)", heritage_text)
                if extends_match:
                    parent_classes.append(extends_match.group(1))
                for impl_match in re.finditer(
                    r"implements\s+([\w,\s]+)", heritage_text
                ):
                    parent_classes.extend(
                        [s.strip() for s in impl_match.group(1).split(",")]
                    )

        # Get decorators (look at preceding siblings)
        prev = node.prev_named_sibling
        while prev and prev.type == "decorator":
            dec_text = source_bytes[prev.start_byte : prev.end_byte].decode("utf-8")
            decorators.insert(0, dec_text)
            prev = prev.prev_named_sibling

        # Get class-level JSDoc
        class_comment = self._get_preceding_comment(node, source_bytes)
        # If decorators exist, the JSDoc might be before the first decorator
        if not class_comment and decorators:
            first_dec = node.prev_named_sibling
            while first_dec and first_dec.type == "decorator":
                prev_of_dec = first_dec.prev_named_sibling
                if prev_of_dec and prev_of_dec.type == "decorator":
                    first_dec = prev_of_dec
                else:
                    break
            if first_dec:
                class_comment = self._get_preceding_comment(first_dec, source_bytes)

        jsdoc = extract_jsdoc_parts(class_comment)

        # Skip @internal classes
        if jsdoc["is_internal"]:
            return

        # Build class summary chunk (properties only, no method bodies)
        class_body = None
        for child in node.children:
            if child.type == "class_body":
                class_body = child
                break

        properties = []
        methods_nodes = []

        if class_body:
            comment_buffer = ""
            for member in class_body.named_children:
                if member.type == "comment":
                    comment_buffer = source_bytes[
                        member.start_byte : member.end_byte
                    ].decode("utf-8", errors="replace")
                    continue

                if member.type in ("public_field_definition", "property_definition"):
                    prop_text = source_bytes[
                        member.start_byte : member.end_byte
                    ].decode("utf-8", errors="replace")
                    properties.append(
                        prop_text.split("\n")[0][:200]
                    )  # First line, max 200 chars
                    comment_buffer = ""
                elif member.type in ("method_definition",):
                    methods_nodes.append((member, comment_buffer))
                    comment_buffer = ""
                elif member.type == "decorator":
                    # Decorators precede methods/properties
                    pass
                else:
                    comment_buffer = ""

        # Create class summary chunk
        summary_text = self._build_class_summary_text(
            class_name, parent_classes, decorators, jsdoc, properties, ctx
        )
        if summary_text:
            line_start = node.start_point[0] + 1
            line_end = node.end_point[0] + 1
            chunks.append(
                {
                    "chunk_type": "class_summary",
                    "class_name": class_name,
                    "parent_classes": parent_classes,
                    "method_name": "",
                    "signature": "",
                    "visibility": "public",
                    "is_deprecated": bool(jsdoc["deprecated"]),
                    "file_path": ctx["file_path"],
                    "module_path": ctx["module_path"],
                    "language": ctx["language"],
                    "version": ctx["version"],
                    "line_start": line_start,
                    "line_end": line_end,
                    "embedding_text": summary_text,
                    "raw_code": source_bytes[
                        node.start_byte : min(node.start_byte + 2000, node.end_byte)
                    ].decode("utf-8", errors="replace"),
                }
            )

        # Extract each method
        for method_node, preceding_comment in methods_nodes:
            self._extract_method(
                method_node,
                preceding_comment,
                source_bytes,
                chunks,
                ctx,
                class_name,
                parent_classes,
            )

    def _extract_method(
        self,
        node,
        preceding_comment: str,
        source_bytes: bytes,
        chunks: list,
        ctx: dict,
        class_name: str,
        parent_classes: list,
    ):
        """Extract a single method into a chunk."""
        # Get method name
        method_name = ""
        signature_parts = []
        visibility = "public"
        is_static = False

        for child in node.children:
            if child.type == "property_identifier":
                method_name = source_bytes[child.start_byte : child.end_byte].decode(
                    "utf-8"
                )
            elif child.type == "accessibility_modifier":
                visibility = source_bytes[child.start_byte : child.end_byte].decode(
                    "utf-8"
                )
            elif child.type == "formal_parameters":
                signature_parts.append(
                    source_bytes[child.start_byte : child.end_byte].decode("utf-8")
                )
            elif child.type == "type_annotation":
                signature_parts.append(
                    source_bytes[child.start_byte : child.end_byte].decode("utf-8")
                )
            elif child.type == "type_parameters":
                signature_parts.append(
                    source_bytes[child.start_byte : child.end_byte].decode("utf-8")
                )

        # Check for static keyword
        raw_method_text = source_bytes[node.start_byte : node.end_byte].decode(
            "utf-8", errors="replace"
        )
        if (
            raw_method_text.lstrip().startswith("static ")
            or " static " in raw_method_text[:100]
        ):
            is_static = True

        # Get JSDoc
        if not preceding_comment:
            preceding_comment = self._get_preceding_comment(node, source_bytes)
        jsdoc = extract_jsdoc_parts(preceding_comment)

        # Skip internal methods
        if jsdoc["is_internal"] or jsdoc["is_engine_internal"]:
            return
        # Skip private methods (names starting with __)
        if method_name.startswith("__"):
            return

        # Build signature string
        sig = f"{method_name}{''.join(signature_parts)}"

        # Build embedding text
        embedding_text = self._build_method_embedding_text(
            class_name, method_name, sig, jsdoc, visibility, is_static, ctx
        )

        if not embedding_text:
            return

        line_start = node.start_point[0] + 1
        line_end = node.end_point[0] + 1

        chunks.append(
            {
                "chunk_type": "method",
                "class_name": class_name,
                "parent_classes": parent_classes,
                "method_name": method_name,
                "signature": sig[:500],
                "visibility": visibility,
                "is_deprecated": bool(jsdoc["deprecated"]),
                "file_path": ctx["file_path"],
                "module_path": ctx["module_path"],
                "language": ctx["language"],
                "version": ctx["version"],
                "line_start": line_start,
                "line_end": line_end,
                "embedding_text": embedding_text,
                "raw_code": raw_method_text[:3000],
            }
        )

    def _extract_enum(self, node, source_bytes: bytes, chunks: list, ctx: dict):
        """Extract an enum declaration as a single chunk."""
        enum_name = ""
        for child in node.children:
            if child.type == "identifier":
                enum_name = source_bytes[child.start_byte : child.end_byte].decode(
                    "utf-8"
                )
                break

        comment = self._get_preceding_comment(node, source_bytes)
        jsdoc = extract_jsdoc_parts(comment)

        if jsdoc["is_internal"]:
            return

        raw = source_bytes[node.start_byte : node.end_byte].decode(
            "utf-8", errors="replace"
        )

        desc = jsdoc["description_zh"] or jsdoc["description_en"] or ""
        embedding_text = f"Module: {ctx['file_path']}\nEnum: {enum_name}\n\n"
        if desc:
            embedding_text += f"{desc}\n\n"
        embedding_text += raw[:2000]

        line_start = node.start_point[0] + 1
        line_end = node.end_point[0] + 1

        chunks.append(
            {
                "chunk_type": "enum",
                "class_name": enum_name,
                "parent_classes": [],
                "method_name": "",
                "signature": "",
                "visibility": "public",
                "is_deprecated": bool(jsdoc["deprecated"]),
                "file_path": ctx["file_path"],
                "module_path": ctx["module_path"],
                "language": ctx["language"],
                "version": ctx["version"],
                "line_start": line_start,
                "line_end": line_end,
                "embedding_text": embedding_text,
                "raw_code": raw[:3000],
            }
        )

    def _extract_top_level_function(
        self, node, source_bytes: bytes, chunks: list, ctx: dict
    ):
        """Extract a standalone top-level function."""
        func_name = ""
        sig = ""

        if node.type == "function_declaration":
            for child in node.children:
                if child.type == "identifier":
                    func_name = source_bytes[child.start_byte : child.end_byte].decode(
                        "utf-8"
                    )
                elif child.type == "formal_parameters":
                    sig = source_bytes[child.start_byte : child.end_byte].decode(
                        "utf-8"
                    )
        elif node.type == "lexical_declaration":
            # const foo = (...) => {...} or const foo = function(...)
            raw = source_bytes[node.start_byte : node.end_byte].decode(
                "utf-8", errors="replace"
            )
            match = re.match(r"(?:export\s+)?(?:const|let|var)\s+(\w+)", raw)
            if match:
                func_name = match.group(1)
            else:
                return  # Can't extract name

        if not func_name:
            return

        comment = self._get_preceding_comment(node, source_bytes)
        jsdoc = extract_jsdoc_parts(comment)

        if jsdoc["is_internal"] or jsdoc["is_engine_internal"]:
            return

        raw = source_bytes[node.start_byte : node.end_byte].decode(
            "utf-8", errors="replace"
        )

        desc_zh = jsdoc["description_zh"]
        desc_en = jsdoc["description_en"]
        embedding_text = f"Module: {ctx['file_path']}\nFunction: {func_name}\n"
        if sig:
            embedding_text += f"Signature: {func_name}{sig}\n"
        embedding_text += "\n"
        if desc_en:
            embedding_text += f"{desc_en}\n"
        if desc_zh:
            embedding_text += f"{desc_zh}\n"

        line_start = node.start_point[0] + 1
        line_end = node.end_point[0] + 1

        chunks.append(
            {
                "chunk_type": "function",
                "class_name": "",
                "parent_classes": [],
                "method_name": func_name,
                "signature": f"{func_name}{sig}"[:500],
                "visibility": "public",
                "is_deprecated": bool(jsdoc["deprecated"]),
                "file_path": ctx["file_path"],
                "module_path": ctx["module_path"],
                "language": ctx["language"],
                "version": ctx["version"],
                "line_start": line_start,
                "line_end": line_end,
                "embedding_text": embedding_text,
                "raw_code": raw[:3000],
            }
        )

    def _extract_type_declaration(
        self, node, source_bytes: bytes, chunks: list, ctx: dict
    ):
        """Extract interface or type alias declarations."""
        name = ""
        for child in node.children:
            if child.type in ("type_identifier", "identifier"):
                name = source_bytes[child.start_byte : child.end_byte].decode("utf-8")
                break

        if not name:
            return

        comment = self._get_preceding_comment(node, source_bytes)
        jsdoc = extract_jsdoc_parts(comment)

        if jsdoc["is_internal"]:
            return

        raw = source_bytes[node.start_byte : node.end_byte].decode(
            "utf-8", errors="replace"
        )
        chunk_type = (
            "interface" if node.type == "interface_declaration" else "type_alias"
        )

        desc = jsdoc["description_zh"] or jsdoc["description_en"] or ""
        embedding_text = f"Module: {ctx['file_path']}\n{chunk_type.replace('_', ' ').title()}: {name}\n\n"
        if desc:
            embedding_text += f"{desc}\n\n"
        embedding_text += raw[:2000]

        line_start = node.start_point[0] + 1
        line_end = node.end_point[0] + 1

        chunks.append(
            {
                "chunk_type": chunk_type,
                "class_name": name,
                "parent_classes": [],
                "method_name": "",
                "signature": "",
                "visibility": "public",
                "is_deprecated": bool(jsdoc["deprecated"]),
                "file_path": ctx["file_path"],
                "module_path": ctx["module_path"],
                "language": ctx["language"],
                "version": ctx["version"],
                "line_start": line_start,
                "line_end": line_end,
                "embedding_text": embedding_text,
                "raw_code": raw[:3000],
            }
        )

    def _build_class_summary_text(
        self, class_name, parent_classes, decorators, jsdoc, properties, ctx
    ):
        """Build the embedding text for a class summary chunk."""
        parts = [f"Module: {ctx['file_path']}"]
        inheritance = (
            f" (extends {', '.join(parent_classes)})" if parent_classes else ""
        )
        parts.append(f"Class: {class_name}{inheritance}")
        parts.append("")

        if jsdoc["description_en"]:
            parts.append(jsdoc["description_en"])
        if jsdoc["description_zh"]:
            parts.append(jsdoc["description_zh"])
        if jsdoc["deprecated"]:
            parts.append(f"@deprecated {jsdoc['deprecated']}")
        parts.append("")

        if properties:
            parts.append("Properties:")
            for prop in properties[:30]:  # Max 30 properties
                parts.append(f"  {prop}")

        return "\n".join(parts)

    def _build_method_embedding_text(
        self, class_name, method_name, sig, jsdoc, visibility, is_static, ctx
    ):
        """Build the embedding text for a method chunk."""
        parts = [f"Module: {ctx['file_path']}"]
        prefix = "Static method" if is_static else "Method"
        if class_name:
            parts.append(f"Class: {class_name}")
            parts.append(f"{prefix}: {method_name}")
        else:
            parts.append(f"Function: {method_name}")
        parts.append("")

        if jsdoc["description_en"]:
            parts.append(jsdoc["description_en"])
        if jsdoc["description_zh"]:
            parts.append(jsdoc["description_zh"])
        parts.append("")

        if sig:
            parts.append(f"Signature: {sig[:500]}")

        if jsdoc["params"]:
            parts.append("Parameters:")
            for p in jsdoc["params"]:
                parts.append(f"  - {p['name']}: {p['desc']}")

        if jsdoc["returns"]:
            parts.append(f"Returns: {jsdoc['returns']}")

        if jsdoc["examples"]:
            parts.append(f"Example: {jsdoc['examples'][0][:300]}")

        if jsdoc["deprecated"]:
            parts.append(f"@deprecated {jsdoc['deprecated']}")

        return "\n".join(parts)

    def _make_file_chunk(
        self, source: str, rel_path: str, module_path: str, version: str
    ) -> Dict:
        """Create a single chunk for a small file."""
        return {
            "chunk_type": "file",
            "class_name": "",
            "parent_classes": [],
            "method_name": "",
            "signature": "",
            "visibility": "public",
            "is_deprecated": False,
            "file_path": rel_path,
            "module_path": module_path,
            "language": "typescript",
            "version": version,
            "line_start": 1,
            "line_end": source.count("\n") + 1,
            "embedding_text": f"Module: {rel_path}\n\n{source[:3000]}",
            "raw_code": source[:3000],
        }


# ---------------------------------------------------------------------------
# Tree-sitter C++ parser
# ---------------------------------------------------------------------------


class CppCodeParser:
    """Parses C++ source files into structured code chunks."""

    def __init__(self):
        self.parser = Parser(CPP_LANGUAGE)

    def parse_file(
        self, file_path: str, version: str, base_dir: str
    ) -> List[Dict[str, Any]]:
        """Parse a single C++ file into code chunks."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()
        except Exception as e:
            logger.warning(f"Failed to read {file_path}: {e}")
            return []

        if not source.strip():
            return []

        rel_path = os.path.relpath(file_path, base_dir).replace("\\", "/")
        module_path = rel_path.replace("/", ".").replace(".cpp", "").replace(".h", "")

        source_bytes = source.encode("utf-8")
        tree = self.parser.parse(source_bytes)
        root = tree.root_node

        chunks: List[Dict[str, Any]] = []
        state = {"nodes_visited": 0}
        ctx = {
            "file_path": rel_path,
            "module_path": module_path,
            "version": version,
            "language": "cpp",
        }
        try:
            self._walk(root, source_bytes, chunks, ctx, state)
        except ParserBudgetExceeded as e:
            logger.warning(f"Parser budget exceeded for {rel_path}: {e}")

        # Small file fallback
        if not chunks and len(source) < 4000:
            chunks.append(
                {
                    "chunk_type": "file",
                    "class_name": "",
                    "parent_classes": [],
                    "method_name": "",
                    "signature": "",
                    "visibility": "public",
                    "is_deprecated": False,
                    "file_path": rel_path,
                    "module_path": module_path,
                    "language": "cpp",
                    "version": version,
                    "line_start": 1,
                    "line_end": source.count("\n") + 1,
                    "embedding_text": f"Module: {rel_path}\n\n{source[:3000]}",
                    "raw_code": source[:3000],
                }
            )

        return chunks

    def _walk(self, node, source_bytes: bytes, chunks: list, ctx: dict, state: dict):
        """Recursively walk the C++ AST. See TypeScriptCodeParser._walk for rationale."""
        state["nodes_visited"] += 1
        if state["nodes_visited"] > MAX_NODES_PER_FILE:
            raise ParserBudgetExceeded(f"visited > {MAX_NODES_PER_FILE} nodes")
        if len(chunks) > MAX_CHUNKS_PER_FILE:
            raise ParserBudgetExceeded(f"emitted > {MAX_CHUNKS_PER_FILE} chunks")

        t = node.type

        if t == "class_specifier":
            self._extract_cpp_class(node, source_bytes, chunks, ctx)
            return  # methods emitted inside _extract_cpp_class; do not descend
        if t == "struct_specifier":
            self._extract_cpp_class(node, source_bytes, chunks, ctx, is_struct=True)
            return
        if t == "enum_specifier":
            self._extract_cpp_enum(node, source_bytes, chunks, ctx)
            return
        if t == "function_definition":
            # Top-level function. Methods defined inside a class_specifier are
            # handled by _extract_cpp_class, so we only reach this for truly
            # free functions (template/namespace/translation-unit scope).
            self._extract_cpp_function(node, source_bytes, chunks, ctx)
            return

        # Descend into namespaces, linkage specs, template declarations,
        # translation unit, preproc_if, etc.
        for child in node.named_children:
            self._walk(child, source_bytes, chunks, ctx, state)

    def _get_preceding_comment_cpp(self, node, source_bytes: bytes) -> str:
        """Get Doxygen/block comment preceding a node."""
        prev = node.prev_named_sibling
        if prev and prev.type == "comment":
            text = source_bytes[prev.start_byte : prev.end_byte].decode(
                "utf-8", errors="replace"
            )
            if text.strip().startswith("/**") or text.strip().startswith("///"):
                return text
        return ""

    def _extract_cpp_class(
        self, node, source_bytes: bytes, chunks: list, ctx: dict, is_struct=False
    ):
        """Extract a C++ class/struct."""
        class_name = ""
        parent_classes = []

        for child in node.children:
            if child.type == "type_identifier":
                class_name = source_bytes[child.start_byte : child.end_byte].decode(
                    "utf-8"
                )
            elif child.type == "base_class_clause":
                base_text = source_bytes[child.start_byte : child.end_byte].decode(
                    "utf-8"
                )
                for m in re.finditer(
                    r"(?:public|protected|private)?\s*(\w+)", base_text
                ):
                    base = m.group(1)
                    if base not in ("public", "protected", "private"):
                        parent_classes.append(base)

        if not class_name:
            return

        # Skip forward declarations like `class Camera;` -- they have no body
        # (no field_declaration_list child) and add only noise to the index.
        has_body = any(c.type == "field_declaration_list" for c in node.children)
        if not has_body:
            return

        comment = self._get_preceding_comment_cpp(node, source_bytes)
        jsdoc = extract_jsdoc_parts(comment)

        raw = source_bytes[node.start_byte : node.end_byte].decode(
            "utf-8", errors="replace"
        )

        # Build summary
        kind = "Struct" if is_struct else "Class"
        inheritance = (
            f" (extends {', '.join(parent_classes)})" if parent_classes else ""
        )
        embedding_text = f"Module: {ctx['file_path']}\n{kind}: {class_name}{inheritance}\nLanguage: C++\n\n"
        if jsdoc["description_en"]:
            embedding_text += f"{jsdoc['description_en']}\n"
        if jsdoc["description_zh"]:
            embedding_text += f"{jsdoc['description_zh']}\n"
        # Include the first 2000 chars of the class (declarations in header)
        embedding_text += f"\n{raw[:2000]}"

        line_start = node.start_point[0] + 1
        line_end = node.end_point[0] + 1

        chunks.append(
            {
                "chunk_type": "class_summary",
                "class_name": class_name,
                "parent_classes": parent_classes,
                "method_name": "",
                "signature": "",
                "visibility": "public",
                "is_deprecated": False,
                "file_path": ctx["file_path"],
                "module_path": ctx["module_path"],
                "language": ctx["language"],
                "version": ctx["version"],
                "line_start": line_start,
                "line_end": line_end,
                "embedding_text": embedding_text,
                "raw_code": raw[:3000],
            }
        )

        # Extract methods within the class body
        for child in node.children:
            if child.type == "field_declaration_list":
                for member in child.named_children:
                    if member.type == "function_definition":
                        self._extract_cpp_method(
                            member,
                            source_bytes,
                            chunks,
                            ctx,
                            class_name,
                            parent_classes,
                        )
                    elif member.type == "declaration":
                        # Check if it's a method declaration
                        decl_text = source_bytes[
                            member.start_byte : member.end_byte
                        ].decode("utf-8", errors="replace")
                        if "(" in decl_text and ")" in decl_text:
                            self._extract_cpp_method_decl(
                                member,
                                source_bytes,
                                chunks,
                                ctx,
                                class_name,
                                parent_classes,
                            )

    def _extract_cpp_method(
        self,
        node,
        source_bytes: bytes,
        chunks: list,
        ctx: dict,
        class_name: str,
        parent_classes: list,
    ):
        """Extract a C++ method definition."""
        raw = source_bytes[node.start_byte : node.end_byte].decode(
            "utf-8", errors="replace"
        )
        method_name = ""

        for child in node.children:
            if child.type == "function_declarator":
                for sub in child.children:
                    if sub.type in (
                        "identifier",
                        "field_identifier",
                        "destructor_name",
                    ):
                        method_name = source_bytes[
                            sub.start_byte : sub.end_byte
                        ].decode("utf-8")

        if not method_name:
            return

        comment = self._get_preceding_comment_cpp(node, source_bytes)
        jsdoc = extract_jsdoc_parts(comment)

        embedding_text = f"Module: {ctx['file_path']}\nClass: {class_name}\nMethod: {method_name}\nLanguage: C++\n\n"
        if jsdoc["description_en"]:
            embedding_text += f"{jsdoc['description_en']}\n"
        if jsdoc["description_zh"]:
            embedding_text += f"{jsdoc['description_zh']}\n"
        sig_line = (
            raw.split("{")[0].strip() if "{" in raw else raw.split("\n")[0].strip()
        )
        embedding_text += f"\nSignature: {sig_line[:500]}"

        line_start = node.start_point[0] + 1
        line_end = node.end_point[0] + 1

        chunks.append(
            {
                "chunk_type": "method",
                "class_name": class_name,
                "parent_classes": parent_classes,
                "method_name": method_name,
                "signature": sig_line[:500],
                "visibility": "public",
                "is_deprecated": False,
                "file_path": ctx["file_path"],
                "module_path": ctx["module_path"],
                "language": ctx["language"],
                "version": ctx["version"],
                "line_start": line_start,
                "line_end": line_end,
                "embedding_text": embedding_text,
                "raw_code": raw[:3000],
            }
        )

    def _extract_cpp_method_decl(
        self,
        node,
        source_bytes: bytes,
        chunks: list,
        ctx: dict,
        class_name: str,
        parent_classes: list,
    ):
        """Extract a C++ method declaration (in header)."""
        raw = source_bytes[node.start_byte : node.end_byte].decode(
            "utf-8", errors="replace"
        )
        # Try to extract method name from the declaration
        match = re.search(r"(\w+)\s*\(", raw)
        if not match:
            return
        method_name = match.group(1)
        # Skip type names that look like constructors of other classes
        if method_name in (
            "inline",
            "virtual",
            "static",
            "const",
            "void",
            "int",
            "float",
            "double",
            "bool",
            "auto",
            "explicit",
        ):
            # Try again after these keywords
            remaining = raw[match.end() :]
            match2 = re.search(r"(\w+)\s*\(", raw[match.start() + len(method_name) :])
            if match2:
                method_name = match2.group(1)
            else:
                return

        comment = self._get_preceding_comment_cpp(node, source_bytes)
        jsdoc = extract_jsdoc_parts(comment)

        embedding_text = f"Module: {ctx['file_path']}\nClass: {class_name}\nMethod declaration: {method_name}\nLanguage: C++\n\n"
        if jsdoc["description_en"]:
            embedding_text += f"{jsdoc['description_en']}\n"
        if jsdoc["description_zh"]:
            embedding_text += f"{jsdoc['description_zh']}\n"
        embedding_text += f"\nDeclaration: {raw.strip()[:500]}"

        line_start = node.start_point[0] + 1
        line_end = node.end_point[0] + 1

        chunks.append(
            {
                "chunk_type": "method",
                "class_name": class_name,
                "parent_classes": parent_classes,
                "method_name": method_name,
                "signature": raw.strip()[:500],
                "visibility": "public",
                "is_deprecated": False,
                "file_path": ctx["file_path"],
                "module_path": ctx["module_path"],
                "language": ctx["language"],
                "version": ctx["version"],
                "line_start": line_start,
                "line_end": line_end,
                "embedding_text": embedding_text,
                "raw_code": raw[:3000],
            }
        )

    def _extract_cpp_function(self, node, source_bytes: bytes, chunks: list, ctx: dict):
        """Extract a top-level C++ function."""
        raw = source_bytes[node.start_byte : node.end_byte].decode(
            "utf-8", errors="replace"
        )
        func_name = ""

        for child in node.children:
            if child.type == "function_declarator":
                for sub in child.children:
                    if sub.type in ("identifier", "qualified_identifier"):
                        func_name = source_bytes[sub.start_byte : sub.end_byte].decode(
                            "utf-8"
                        )

        if not func_name:
            return

        comment = self._get_preceding_comment_cpp(node, source_bytes)
        jsdoc = extract_jsdoc_parts(comment)

        sig_line = (
            raw.split("{")[0].strip() if "{" in raw else raw.split("\n")[0].strip()
        )

        embedding_text = (
            f"Module: {ctx['file_path']}\nFunction: {func_name}\nLanguage: C++\n\n"
        )
        if jsdoc["description_en"]:
            embedding_text += f"{jsdoc['description_en']}\n"
        if jsdoc["description_zh"]:
            embedding_text += f"{jsdoc['description_zh']}\n"
        embedding_text += f"\nSignature: {sig_line[:500]}"

        line_start = node.start_point[0] + 1
        line_end = node.end_point[0] + 1

        chunks.append(
            {
                "chunk_type": "function",
                "class_name": "",
                "parent_classes": [],
                "method_name": func_name,
                "signature": sig_line[:500],
                "visibility": "public",
                "is_deprecated": False,
                "file_path": ctx["file_path"],
                "module_path": ctx["module_path"],
                "language": ctx["language"],
                "version": ctx["version"],
                "line_start": line_start,
                "line_end": line_end,
                "embedding_text": embedding_text,
                "raw_code": raw[:3000],
            }
        )

    def _extract_cpp_enum(self, node, source_bytes: bytes, chunks: list, ctx: dict):
        """Extract a C++ enum."""
        enum_name = ""
        for child in node.children:
            if child.type == "type_identifier":
                enum_name = source_bytes[child.start_byte : child.end_byte].decode(
                    "utf-8"
                )
                break

        if not enum_name:
            return

        raw = source_bytes[node.start_byte : node.end_byte].decode(
            "utf-8", errors="replace"
        )
        comment = self._get_preceding_comment_cpp(node, source_bytes)
        jsdoc = extract_jsdoc_parts(comment)

        embedding_text = (
            f"Module: {ctx['file_path']}\nEnum: {enum_name}\nLanguage: C++\n\n"
        )
        if jsdoc["description_en"]:
            embedding_text += f"{jsdoc['description_en']}\n"
        if jsdoc["description_zh"]:
            embedding_text += f"{jsdoc['description_zh']}\n"
        embedding_text += f"\n{raw[:2000]}"

        line_start = node.start_point[0] + 1
        line_end = node.end_point[0] + 1

        chunks.append(
            {
                "chunk_type": "enum",
                "class_name": enum_name,
                "parent_classes": [],
                "method_name": "",
                "signature": "",
                "visibility": "public",
                "is_deprecated": False,
                "file_path": ctx["file_path"],
                "module_path": ctx["module_path"],
                "language": ctx["language"],
                "version": ctx["version"],
                "line_start": line_start,
                "line_end": line_end,
                "embedding_text": embedding_text,
                "raw_code": raw[:3000],
            }
        )


# ---------------------------------------------------------------------------
# Orchestrator: process entire engine directory
# ---------------------------------------------------------------------------

# File extensions to skip entirely
SKIP_EXTENSIONS = {
    ".json",
    ".md",
    ".txt",
    ".yml",
    ".yaml",
    ".toml",
    ".cfg",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".mp3",
    ".wav",
    ".ogg",
    ".zip",
    ".tar",
    ".gz",
    ".map",
    ".min.js",
    ".d.ts",
    ".glsl",
    ".vert",
    ".frag",
    ".chunk",
    ".effect",
}

# Directories to skip
SKIP_DIRS = {
    "node_modules",
    ".git",
    "test",
    "tests",
    "__pycache__",
    "external",
    "vendor",
    "templates",
    "scripts",
    "licenses",
    "docs",
    "platforms",
    "editor",
    ".github",
}


def generate_code_chunk_id(chunk: Dict[str, Any]) -> str:
    """Generate a deterministic chunk ID from file path + content."""
    path_hash = hashlib.md5(chunk["file_path"].encode("utf-8")).hexdigest()[:12]
    content_hash = hashlib.md5(chunk["embedding_text"].encode("utf-8")).hexdigest()[:12]
    return f"{path_hash}_{content_hash}"


def process_engine_directory(
    engine_dir: str,
    output_file: str,
    version: str,
) -> int:
    """
    Process an entire engine directory (TS + C++) and write chunks to JSONL.

    Returns the total number of chunks written.
    """
    ts_parser = TypeScriptCodeParser()
    cpp_parser = CppCodeParser()

    total_chunks = 0
    ts_files = 0
    cpp_files = 0

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as out_f:
        for root, dirs, files in os.walk(engine_dir):
            # Skip unwanted directories
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

            for filename in files:
                file_path = os.path.join(root, filename)
                ext = os.path.splitext(filename)[1].lower()

                if ext in SKIP_EXTENSIONS:
                    continue

                chunks = []

                if ext == ".ts" and not filename.endswith(".d.ts"):
                    chunks = ts_parser.parse_file(file_path, version, engine_dir)
                    ts_files += 1
                elif ext in (".cpp", ".h", ".hpp", ".cc"):
                    chunks = cpp_parser.parse_file(file_path, version, engine_dir)
                    cpp_files += 1
                else:
                    continue

                for chunk in chunks:
                    chunk["chunk_id"] = generate_code_chunk_id(chunk)
                    out_f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                    total_chunks += 1

            # Log progress every 100 files
            if (ts_files + cpp_files) % 100 == 0 and (ts_files + cpp_files) > 0:
                logger.info(
                    f"Processed {ts_files} TS + {cpp_files} C++ files, {total_chunks} chunks so far..."
                )

    logger.info(
        f"Done processing {version}: {ts_files} TS files + {cpp_files} C++ files = {total_chunks} chunks"
    )
    return total_chunks


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Parse Cocos Creator engine source code into chunks for RAG indexing"
    )
    parser.add_argument(
        "--version",
        choices=["3.7.3", "3.8.8", "all"],
        default="all",
        help="Engine version to process",
    )
    args = parser.parse_args()

    versions = ["3.7.3", "3.8.8"] if args.version == "all" else [args.version]

    for version in versions:
        engine_dir = os.path.join(".data", "engine", version)
        output_file = os.path.join(".data", "processed", f"code_chunks_{version}.jsonl")

        if not os.path.exists(engine_dir):
            logger.error(f"Engine directory not found: {engine_dir}")
            logger.error(f"Please clone the engine first:")
            logger.error(
                f"  git clone --depth 1 --branch {version} https://github.com/cocos/cocos-engine.git {engine_dir}"
            )
            continue

        logger.info(f"Processing engine {version} from {engine_dir}...")
        total = process_engine_directory(engine_dir, output_file, version)
        logger.info(f"Wrote {total} chunks to {output_file}")


if __name__ == "__main__":
    main()
