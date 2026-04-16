import os
import sys
import pytest
from chromadb.config import Settings

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
)

from core.vector_store import VectorStoreManager


@pytest.fixture
def vector_store(tmp_path):
    import core.db as db

    original_get = db.get_chroma_client

    def mock_get_client():
        import chromadb

        return chromadb.PersistentClient(
            path=str(tmp_path), settings=Settings(anonymized_telemetry=False)
        )

    db.get_chroma_client = mock_get_client

    store = VectorStoreManager()

    yield store

    db.get_chroma_client = original_get


def test_get_or_create_collection(vector_store):
    col = vector_store.get_or_create_collection("3.8.8")
    assert col.name == "cocos_3_8_8"
    assert "description" in col.metadata


def test_add_documents(vector_store):
    version = "3.7.3"
    ids = ["doc1", "doc2"]
    documents = ["Cocos test 1", "Cocos test 2"]
    metadatas = [
        {"url": "url1", "version": version},
        {"url": "url2", "version": version},
    ]
    embeddings = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

    vector_store.add_documents(version, ids, documents, metadatas, embeddings)

    existing = vector_store.get_existing_ids(version)
    assert "doc1" in existing
    assert "doc2" in existing
    assert len(existing) == 2
