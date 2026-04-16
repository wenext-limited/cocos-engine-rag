import os
import chromadb
from chromadb.config import Settings


def get_chroma_client():
    persist_directory = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "chroma_db"
    )
    return chromadb.PersistentClient(
        path=persist_directory, settings=Settings(anonymized_telemetry=False)
    )
