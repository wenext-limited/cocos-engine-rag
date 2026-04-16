import os
from chromadb.api.types import EmbeddingFunction
from src.core.db import get_chroma_client


class VectorStoreManager:
    def __init__(self):
        self.client = get_chroma_client()

    def get_or_create_collection(self, version: str):
        collection_name = f"cocos_{version.replace('.', '_')}"
        return self.client.get_or_create_collection(
            name=collection_name,
            metadata={"description": f"Cocos Creator {version} documentation"},
        )

    def add_documents(
        self,
        version: str,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict],
        embeddings: list[list[float]] = None,
    ):
        collection = self.get_or_create_collection(version)
        if embeddings:
            collection.add(
                ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings
            )
        else:
            collection.add(ids=ids, documents=documents, metadatas=metadatas)

    def get_existing_ids(self, version: str) -> set[str]:
        collection = self.get_or_create_collection(version)
        result = collection.get(include=[])
        return set(result["ids"])
