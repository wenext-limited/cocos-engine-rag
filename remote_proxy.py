# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "httpx",
# ]
# ///

import asyncio
import sys
import json
import httpx
import traceback
from urllib.parse import urljoin

# Force UTF-8 for stdio to avoid encoding issues on Windows
sys.stdout.reconfigure(encoding='utf-8')
sys.stdin.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

async def proxy_sse_to_stdio(sse_url: str):
    headers = {"Host": "localhost:18000"}
    
    async with httpx.AsyncClient(timeout=None) as client:
        try:
            async with client.stream("GET", sse_url, headers=headers) as response:
                if response.status_code != 200:
                    print(f"Error connecting to SSE: {response.status_code}", file=sys.stderr)
                    return
                
                post_endpoint = None
                
                async def read_sse():
                    nonlocal post_endpoint
                    buffer = ""
                    async for chunk in response.aiter_text():
                        buffer += chunk.replace("\r\n", "\n").replace("\r", "\n")
                        while "\n\n" in buffer:
                            event_block, buffer = buffer.split("\n\n", 1)
                            lines = event_block.split("\n")
                            event_type = "message"
                            data_lines = []
                            for line in lines:
                                if line.startswith("event: "):
                                    event_type = line[7:]
                                elif line.startswith("data: "):
                                    data_lines.append(line[6:])
                            data = "\n".join(data_lines)
                            
                            if event_type == "endpoint":
                                post_endpoint = urljoin(sse_url, data)
                                print(f"Connected. Post endpoint: {post_endpoint}", file=sys.stderr)
                            elif event_type == "message" and data:
                                try:
                                    sys.stdout.write(data + "\n")
                                    sys.stdout.flush()
                                except Exception:
                                    pass
                                    
                async def read_stdin():
                    loop = asyncio.get_running_loop()
                    while True:
                        line = await loop.run_in_executor(None, sys.stdin.readline)
                        if not line:
                            break
                        line = line.strip()
                        if not line:
                            continue
                            
                        # Wait for endpoint
                        while not post_endpoint:
                            await asyncio.sleep(0.1)
                            
                        try:
                            req = json.loads(line)
                            if req.get("method") == "tools/call" and "params" in req and "arguments" in req["params"]:
                                args = req["params"]["arguments"]
                                if "openai_api_key" in args:
                                    del args["openai_api_key"]
                                    line = json.dumps(req)
                        except Exception:
                            pass
                            
                        try:
                            post_headers = {**headers, "Content-Type": "application/json"}
                            resp = await client.post(post_endpoint, content=line, headers=post_headers)
                            if resp.status_code >= 400:
                                print(f"POST Error: {resp.status_code} {resp.text}", file=sys.stderr)
                        except Exception as e:
                            print(f"POST Exception: {e}", file=sys.stderr)
                
                await asyncio.gather(read_sse(), read_stdin())
        except Exception as e:
            print(f"Connection failed: {e}", file=sys.stderr)

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://43.134.44.85:18000/sse"
    asyncio.run(proxy_sse_to_stdio(url))
