import json
import logging
import time
from typing import List, Dict, Any
import openai

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, api_key: str = None, model: str = "text-embedding-3-small"):
        if api_key:
            openai.api_key = api_key
        self.model = model

    def get_embeddings(
        self, texts: List[str], batch_size: int = 100
    ) -> List[List[float]]:
        embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            try:
                response = openai.embeddings.create(input=batch, model=self.model)
                embeddings.extend([data.embedding for data in response.data])
            except Exception as e:
                logger.error(f"Error generating embeddings: {e}")
                raise
            time.sleep(0.5)  # Basic rate limiting
        return embeddings
