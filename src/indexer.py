from core.config import load_env
from core.db import get_chroma_client

if __name__ == "__main__":
    load_env()
    print("Indexer initialized. Chroma client ready.")
