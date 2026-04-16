import os
import time
import urllib.parse
from collections import deque
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup


def get_file_path(base_dir, url):
    parsed = urllib.parse.urlparse(url)
    path = parsed.path
    if path.endswith("/"):
        path += "index.html"
    if not path.endswith(".html"):
        path += ".html"

    # Remove leading slash for safe join
    if path.startswith("/"):
        path = path[1:]

    return os.path.join(base_dir, path)


def crawl_docs(start_url, base_dir, version_prefix, delay=0.5):
    print(f"Starting crawl of {start_url} into {base_dir}")
    os.makedirs(base_dir, exist_ok=True)

    queue = deque([start_url])
    visited = set([start_url])

    session = requests.Session()
    session.headers.update({"User-Agent": "CocosRAGCrawler/1.0 (Python/requests)"})

    retry_strategy = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    while queue:
        url = queue.popleft()

        file_path = get_file_path(base_dir, url)

        # Check if we already have it (resuming)
        if os.path.exists(file_path):
            print(f"Skipping (already downloaded): {url}")
            # Even if skipped, we should extract links?
            # Actually, to properly resume and discover other links, we should ideally read the local file to find links.
            # But let's read the local file instead of re-downloading
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    html = f.read()
            except Exception as e:
                print(f"Error reading local file {file_path}: {e}")
                continue
        else:
            print(f"Downloading: {url}")
            try:
                response = session.get(url, timeout=10)
                response.raise_for_status()
                html = response.text

                # Save to disk
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(html)

                time.sleep(delay)
            except Exception as e:
                print(f"Failed to download {url}: {e}")
                continue

        # Parse links
        soup = BeautifulSoup(html, "html.parser")
        for link in soup.find_all("a"):
            href = link.get("href")
            if not href:
                continue

            # Normalize URL
            next_url = urllib.parse.urljoin(url, href)

            # Remove fragments
            next_url = urllib.parse.urlunparse(
                urllib.parse.urlparse(next_url)._replace(fragment="")
            )

            # Check if it's within the same version domain
            if next_url.startswith(version_prefix) and next_url not in visited:
                visited.add(next_url)
                queue.append(next_url)


if __name__ == "__main__":
    versions = [
        {
            "start_url": "https://docs.cocos.com/creator/3.7/manual/zh/",
            "prefix": "https://docs.cocos.com/creator/3.7/manual/zh/",
            "dir": ".data/raw/3.7.3",
        },
        {
            "start_url": "https://docs.cocos.com/creator/3.8/manual/zh/",
            "prefix": "https://docs.cocos.com/creator/3.8/manual/zh/",
            "dir": ".data/raw/3.8.8",
        },
    ]

    for v in versions:
        crawl_docs(v["start_url"], v["dir"], v["prefix"])
