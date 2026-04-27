import json
import logging
import time
from typing import List, Dict, Any
import openai
import httpx

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, api_key: str = None, model: str = "text-embedding-3-small"):
        if api_key:
            openai.api_key = api_key
        self.model = model
        
        # Add debugging for HTTP requests
        self._http_client = httpx.Client(
            event_hooks={'request': [lambda r: logger.info(f"Req: {r.method} {r.url}")],
                         'response': [lambda r: logger.info(f"Res: {r.status_code} {r.url}")]},
            timeout=15.0 # Set explicit timeout so it fails fast instead of hanging
        )
        openai.http_client = self._http_client

    def get_embeddings(
        self, texts: List[str], batch_size: int = 100
    ) -> List[List[float]]:
        # Max chars per batch as a safe heuristic for 300,000 tokens limit.
        # 1 Chinese character is roughly 1-3 tokens.
        MAX_CHARS_PER_BATCH = 100_000

        embeddings = []

        # dynamic batching
        batches = []
        current_batch = []
        current_chars = 0

        for text in texts:
            text_len = len(text)
            if current_chars + text_len > MAX_CHARS_PER_BATCH and current_batch:
                batches.append(current_batch)
                current_batch = [text]
                current_chars = text_len
            elif len(current_batch) >= batch_size:
                batches.append(current_batch)
                current_batch = [text]
                current_chars = text_len
            else:
                current_batch.append(text)
                current_chars += text_len

        if current_batch:
            batches.append(current_batch)

        for idx, batch in enumerate(batches):
            try:
                logger.info(f"Sending batch {idx} with {len(batch)} items to model {self.model}...")
                start_t = time.time()
                response = openai.embeddings.create(input=batch, model=self.model)
                logger.info(f"Batch {idx} succeeded in {time.time()-start_t:.2f}s")
                embeddings.extend([data.embedding for data in response.data])
            except Exception as e:
                logger.error(
                    f"Error generating embeddings for batch {idx} ({len(batch)} items): {e}"
                )
                logger.warning(f"Falling back to individual embedding for batch {idx}")
                for text in batch:
                    try:
                        resp = openai.embeddings.create(input=[text], model=self.model)
                        embeddings.extend([data.embedding for data in resp.data])
                        time.sleep(0.1)
                    except Exception as inner_e:
                        logger.error(
                            f"Failed to embed single text ({len(text)} chars): {inner_e}"
                        )
                        raise inner_e
            time.sleep(0.2)  # Basic rate limiting

        return embeddings
