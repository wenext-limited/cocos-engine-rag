import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
)

from core.embedding import EmbeddingService


@patch("core.embedding.openai")
@patch("core.embedding.time.sleep")
def test_embedding_service(mock_sleep, mock_openai):
    # Setup mock
    mock_response = MagicMock()
    mock_data = MagicMock()
    mock_data.embedding = [0.1, 0.2, 0.3]
    mock_response.data = [mock_data]
    mock_openai.embeddings.create.return_value = mock_response

    service = EmbeddingService(api_key="test-key")

    texts = ["Cocos test"]
    embeddings = service.get_embeddings(texts)

    assert len(embeddings) == 1
    assert embeddings[0] == [0.1, 0.2, 0.3]
    mock_openai.embeddings.create.assert_called_once()
