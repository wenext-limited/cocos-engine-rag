"""
Source code indexer for Cocos Creator engine.

Reads code chunks from JSONL (produced by code_parser.py), generates embeddings
via OpenAI, and stores them in separate ChromaDB collections (code_3_7_3, code_3_8_8).
Supports resume — already-indexed chunks are skipped automatically.
"""

import json
import os
import argparse
import logging
import hashlib
from typing import List, Dict, Any

from core.config import load_env
from core.vector_store import VectorStoreManager
from core.embedding import EmbeddingService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def process_code_file(
    file_path: str,
    version: str,
    vector_store: VectorStoreManager,
    embedding_service: EmbeddingService,
    batch_size: int = 100,
):
    """Process a code chunks JSONL file and index into ChromaDB."""
    collection_name = f"code_{version.replace('.', '_')}"
    logger.info(f"Processing code embeddings for {version} from {file_path}")
    logger.info(f"Target collection: {collection_name}")

    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return

    # Get existing IDs to support resume
    existing_ids = vector_store.get_existing_ids_for_collection(collection_name)
    logger.info(
        f"Found {len(existing_ids)} existing chunks in collection {collection_name}"
    )

    chunks_to_process = []
    ids_to_process = []
    seen_ids = set()

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            chunk = json.loads(line)
            chunk_id = chunk.get("chunk_id", "")

            if not chunk_id:
                continue

            if chunk_id not in existing_ids and chunk_id not in seen_ids:
                chunks_to_process.append(chunk)
                ids_to_process.append(chunk_id)
                seen_ids.add(chunk_id)

    logger.info(f"Found {len(chunks_to_process)} new code chunks to embed")

    if not chunks_to_process:
        logger.info("No new chunks to process")
        return

    for i in range(0, len(chunks_to_process), batch_size):
        batch_chunks = chunks_to_process[i : i + batch_size]
        batch_ids = ids_to_process[i : i + batch_size]

        # Use the embedding_text field for embedding (natural language summary)
        texts_to_embed = [c["embedding_text"] for c in batch_chunks]

        batch_num = i // batch_size + 1
        total_batches = (len(chunks_to_process) + batch_size - 1) // batch_size
        logger.info(
            f"Embedding batch {batch_num}/{total_batches} ({len(batch_chunks)} chunks)"
        )

        try:
            embeddings = embedding_service.get_embeddings(texts_to_embed)

            # Store embedding_text as the document (for BM25 search later)
            documents = texts_to_embed

            # Build metadata (ChromaDB metadata values must be str, int, float, or bool)
            metadatas = []
            for c in batch_chunks:
                metadatas.append(
                    {
                        "chunk_type": c.get("chunk_type", ""),
                        "class_name": c.get("class_name", ""),
                        "parent_classes": ",".join(c.get("parent_classes", [])),
                        "method_name": c.get("method_name", ""),
                        "signature": c.get("signature", "")[:500],
                        "visibility": c.get("visibility", "public"),
                        "is_deprecated": c.get("is_deprecated", False),
                        "file_path": c.get("file_path", ""),
                        "module_path": c.get("module_path", ""),
                        "language": c.get("language", ""),
                        "version": c.get("version", version),
                        "line_start": c.get("line_start", 0),
                        "line_end": c.get("line_end", 0),
                        "raw_code": c.get("raw_code", "")[:3000],
                    }
                )

            vector_store.add_documents_to_collection(
                collection_name=collection_name,
                ids=batch_ids,
                documents=documents,
                metadatas=metadatas,
                embeddings=embeddings,
            )
            logger.info(
                f"Successfully added {len(batch_ids)} code chunks to {collection_name}"
            )
        except Exception as e:
            logger.error(f"Failed to process batch {batch_num}: {e}")
            raise

    logger.info(f"Finished indexing code for version {version}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate embeddings for code chunks and store in ChromaDB"
    )
    parser.add_argument(
        "--version",
        choices=["3.7.3", "3.8.8", "all"],
        default="all",
        help="Engine version to process",
    )
    parser.add_argument(
        "--batch-size", type=int, default=100, help="Batch size for OpenAI API"
    )
    args = parser.parse_args()

    load_env()

    vector_store = VectorStoreManager()
    embedding_service = EmbeddingService()

    versions = ["3.7.3", "3.8.8"] if args.version == "all" else [args.version]

    for version in versions:
        file_path = f".data/processed/code_chunks_{version}.jsonl"
        process_code_file(
            file_path, version, vector_store, embedding_service, args.batch_size
        )


if __name__ == "__main__":
    main()
