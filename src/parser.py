import os
import re
import json
import glob
from bs4 import BeautifulSoup
from typing import List, Dict


def clean_html(soup: BeautifulSoup) -> BeautifulSoup:
    for tag in soup.find_all(["nav", "header", "footer", "script", "style", "aside"]):
        tag.decompose()

    main = soup.find("main")
    if not main:
        main = soup.find("div", class_="content")
    if not main:
        main = soup.find("article")
    if not main:
        main = soup.find("div", class_="book-body")
    if not main:
        main = soup
    return main


def parse_html_to_chunks(html_text: str, url: str, version: str) -> List[Dict]:
    soup = BeautifulSoup(html_text, "html.parser")
    main_node = clean_html(soup)

    # Convert headers to markdown style to preserve them in get_text()
    for i in range(1, 7):
        for h in main_node.find_all(f"h{i}"):
            h.insert_before(f"\n\n{'#' * i} ")
            h.insert_after("\n\n")

    # Add newlines around block elements so they don't merge
    for tag in main_node.find_all(
        ["p", "div", "ul", "ol", "li", "table", "tr", "td", "pre"]
    ):
        tag.insert_before("\n")
        tag.insert_after("\n")

    text = main_node.get_text()
    # Clean up multiple newlines and spaces
    text = re.sub(r" +", " ", text)
    text = re.sub(r"\n\s*\n", "\n\n", text)
    text = text.strip()

    # Now split by markdown headers
    chunks = []
    lines = text.split("\n")
    current_content = []
    breadcrumbs = []

    def add_chunk(url, version, breadcrumbs, content_text):
        if not content_text:
            return

        # OpenAI text-embedding-3-small token limit is 8192.
        # Safe character limit for mixed Chinese/English is around 4000.
        MAX_CHARS = 4000

        if len(content_text) <= MAX_CHARS:
            chunks.append(
                {
                    "url": url,
                    "version": version,
                    "breadcrumbs": list(breadcrumbs),
                    "content": content_text,
                }
            )
        else:
            # Split large content into smaller pieces
            start = 0
            part = 1
            while start < len(content_text):
                end = start + MAX_CHARS
                # Try to break at a newline if possible
                if end < len(content_text):
                    last_newline = content_text.rfind("\n", start, end)
                    if last_newline != -1 and last_newline > start + (MAX_CHARS // 2):
                        end = last_newline

                chunk_part = content_text[start:end].strip()
                if chunk_part:
                    chunks.append(
                        {
                            "url": url,
                            "version": version,
                            "breadcrumbs": list(breadcrumbs) + [f"Part {part}"],
                            "content": chunk_part,
                        }
                    )
                start = end
                part += 1

    for line in lines:
        match = re.match(r"^(#{1,6})\s+(.*)", line.strip())
        if match:
            # We hit a header. Save the previous chunk if any
            if current_content:
                content_text = "\n".join(current_content).strip()
                add_chunk(url, version, breadcrumbs, content_text)
                current_content = []

            level = len(match.group(1))
            header_text = match.group(2).strip()

            # Pop breadcrumbs that are at or deeper than current level
            while len(breadcrumbs) >= level:
                breadcrumbs.pop()
            # Pad if needed (unlikely in well-formed HTML but possible)
            while len(breadcrumbs) < level - 1:
                breadcrumbs.append("")
            breadcrumbs.append(header_text)
        else:
            current_content.append(line)

    if current_content:
        content_text = "\n".join(current_content).strip()
        add_chunk(url, version, breadcrumbs, content_text)

    return chunks


BINARY_FILENAME_PATTERNS = (
    ".zip.html",
    ".tar.gz.html",
    ".rar.html",
    ".7z.html",
    ".exe.html",
    ".dmg.html",
    ".pkg.html",
    ".apk.html",
)

# Minimum readable-text ratio: skip files where >30% of chars are non-printable
BINARY_CONTENT_THRESHOLD = 0.30


def is_binary_html(file_path: str, html_text: str) -> bool:
    """Return True if the file is a binary asset mistakenly saved as .html."""
    fname = os.path.basename(file_path).lower()
    if any(fname.endswith(pat) for pat in BINARY_FILENAME_PATTERNS):
        return True
    # Heuristic: count non-printable / replacement chars in first 4KB
    sample = html_text[:4096]
    if not sample:
        return False
    non_printable = sum(1 for c in sample if ord(c) < 32 and c not in "\n\r\t")
    if non_printable / len(sample) > BINARY_CONTENT_THRESHOLD:
        return True
    return False


def process_directory(input_dir: str, output_file: str, base_url: str, version: str):
    """
    Process all HTML files in a directory and save the chunks to a JSONL file.
    """
    print(f"Processing directory {input_dir} for version {version}...")

    html_files = []
    for root, _, files in os.walk(input_dir):
        for file in files:
            if file.endswith(".html"):
                html_files.append(os.path.join(root, file))

    print(f"Found {len(html_files)} HTML files.")

    total_chunks = 0
    skipped_binary = 0
    with open(output_file, "w", encoding="utf-8") as out_f:
        for file_path in html_files:
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    html_text = f.read()

                if is_binary_html(file_path, html_text):
                    print(f"Skipping binary file: {file_path}")
                    skipped_binary += 1
                    continue

                # Reconstruct URL from file path
                rel_path = os.path.relpath(file_path, input_dir)
                url = base_url + rel_path.replace("\\", "/")

                chunks = parse_html_to_chunks(html_text, url, version)
                for chunk in chunks:
                    out_f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                    total_chunks += 1
            except Exception as e:
                print(f"Error processing {file_path}: {e}")

    if skipped_binary:
        print(f"Skipped {skipped_binary} binary files.")

    print(f"Done. Extracted {total_chunks} chunks to {output_file}")


if __name__ == "__main__":
    # Ensure data output directory exists
    os.makedirs(".data/processed", exist_ok=True)

    # Process 3.7.3
    process_directory(
        input_dir=".data/raw/3.7.3",
        output_file=".data/processed/chunks_3.7.3.jsonl",
        base_url="https://docs.cocos.com/",
        version="3.7.3",
    )

    # Process 3.8.8
    process_directory(
        input_dir=".data/raw/3.8.8",
        output_file=".data/processed/chunks_3.8.8.jsonl",
        base_url="https://docs.cocos.com/",
        version="3.8.8",
    )
