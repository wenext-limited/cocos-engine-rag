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


def generate_chunk_id(chunk: Dict[str, Any]) -> str:
    content_hash = hashlib.md5(chunk["content"].encode("utf-8")).hexdigest()
    url_hash = hashlib.md5(chunk["url"].encode("utf-8")).hexdigest()
    return f"{url_hash}_{content_hash}"


def process_file(
    file_path: str,
    version: str,
    vector_store: VectorStoreManager,
    embedding_service: EmbeddingService,
    batch_size: int = 100,
):
    logger.info(f"Processing embeddings for {version} from {file_path}")

    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return

    existing_ids = vector_store.get_existing_ids(version)
    logger.info(
        f"Found {len(existing_ids)} existing chunks in ChromaDB for version {version}"
    )

    chunks_to_process = []
    ids_to_process = []
    seen_ids = set()

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            chunk = json.loads(line)
            chunk_id = generate_chunk_id(chunk)

            if chunk_id not in existing_ids and chunk_id not in seen_ids:
                chunks_to_process.append(chunk)
                ids_to_process.append(chunk_id)
                seen_ids.add(chunk_id)

    logger.info(f"Found {len(chunks_to_process)} new chunks to embed")

    for i in range(0, len(chunks_to_process), batch_size):
        batch_chunks = chunks_to_process[i : i + batch_size]
        batch_ids = ids_to_process[i : i + batch_size]

        texts_to_embed = [
            f"{' > '.join(c.get('breadcrumbs', []))}\n\n{c['content']}"
            for c in batch_chunks
        ]

        logger.info(
            f"Embedding batch {i // batch_size + 1}/{(len(chunks_to_process) + batch_size - 1) // batch_size}"
        )

        try:
            embeddings = embedding_service.get_embeddings(texts_to_embed)

            documents = texts_to_embed
            metadatas = [
                {
                    "url": c["url"],
                    "version": c["version"],
                    "breadcrumbs": " > ".join(c.get("breadcrumbs", [])),
                }
                for c in batch_chunks
            ]

            vector_store.add_documents(
                version=version,
                ids=batch_ids,
                documents=documents,
                metadatas=metadatas,
                embeddings=embeddings,
            )
            logger.info(f"Successfully added {len(batch_ids)} documents to ChromaDB")
        except Exception as e:
            logger.error(f"Failed to process batch: {e}")
            break


def main():
    parser = argparse.ArgumentParser(
        description="Generate embeddings and store in ChromaDB"
    )
    parser.add_argument(
        "--version",
        choices=["3.7.3", "3.8.8", "all"],
        default="all",
        help="Cocos version to process",
    )
    parser.add_argument(
        "--batch-size", type=int, default=100, help="Batch size for OpenAI API"
    )
    args = parser.parse_args()

    load_env()

    vector_store = VectorStoreManager()
    embedding_service = EmbeddingService()

    versions_to_process = (
        ["3.7.3", "3.8.8"] if args.version == "all" else [args.version]
    )

    for version in versions_to_process:
        file_path = f".data/processed/chunks_{version}.jsonl"
        process_file(
            file_path, version, vector_store, embedding_service, args.batch_size
        )


if __name__ == "__main__":
    main()
