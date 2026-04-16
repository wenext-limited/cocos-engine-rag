import os
import sys

# Setup PYTHONPATH safely
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
)


def test_indexer_imports():
    assert os.path.exists("src/indexer.py")
    assert os.path.exists("src/server.py")
    assert os.path.exists("README.md")

    # Check imports
    import core.db

    assert hasattr(core.db, "get_chroma_client")
