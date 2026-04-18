import os
from chromadb.api.types import EmbeddingFunction
from core.db import get_chroma_client


class VectorStoreManager:
    def __init__(self):
        self.client = get_chroma_client()

    # ---- Existing doc collection helpers (unchanged) ----

    def get_or_create_collection(self, version: str):
        """Get or create a documentation collection for a version."""
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

    # ---- New: generic collection helpers for code collections ----

    def get_or_create_named_collection(
        self, collection_name: str, description: str = ""
    ):
        """Get or create a collection by explicit name."""
        return self.client.get_or_create_collection(
            name=collection_name,
            metadata={"description": description},
        )

    def add_documents_to_collection(
        self,
        collection_name: str,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict],
        embeddings: list[list[float]] = None,
    ):
        """Add documents to a named collection."""
        collection = self.get_or_create_named_collection(collection_name)
        if embeddings:
            collection.add(
                ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings
            )
        else:
            collection.add(ids=ids, documents=documents, metadatas=metadatas)

    def get_existing_ids_for_collection(self, collection_name: str) -> set[str]:
        """Get existing document IDs from a named collection."""
        collection = self.get_or_create_named_collection(collection_name)
        result = collection.get(include=[])
        return set(result["ids"])

    def delete_collection(self, collection_name: str) -> bool:
        """Delete a collection by name. Returns True if it existed."""
        try:
            self.client.delete_collection(name=collection_name)
            return True
        except Exception:
            return False
