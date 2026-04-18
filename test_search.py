import json
import logging
from core.search import SearchService
from core.config import load_env


def test_query():
    # Disable verbose HTTP logging for cleaner output
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("core.search").setLevel(logging.WARNING)

    load_env()
    search_service = SearchService()

    queries = ["如何在 Cocos Creator 中播放音频？", "预制体 (Prefab) 怎么创建？"]

    for query in queries:
        print(f"\n{'=' * 50}")
        print(f"Test Query: {query}")
        print(f"{'=' * 50}")

        # 3.7.3 has finished embedding, so we test on 3.7.3
        results = search_service.search(query=query, version="3.7.3", top_k=2)

        if not results:
            print("No results found.")
            continue

        for i, res in enumerate(results):
            print(f"\nResult {i + 1} (Score: {res['relevance_score']:.4f})")
            print(f"URL: {res['source_url']}")

            try:
                # Assuming the chroma metadata was somehow encoded as latin-1 or similar during scraping/saving
                # Let's fix the presentation for the test script
                try:
                    title = res["section_title"].encode("latin-1").decode("utf-8")
                    content = (
                        res["content"][:250]
                        .replace(chr(10), " ")
                        .encode("latin-1")
                        .decode("utf-8")
                    )
                except Exception:
                    title = res["section_title"]
                    content = res["content"][:250].replace(chr(10), " ")

                print(f"Title: {title}")
                print(f"Content: {content}...")
            except Exception:
                pass


if __name__ == "__main__":
    test_query()
