import os
from dotenv import load_dotenv

def load_env():
    load_dotenv()
    # Set the custom base URL for the litellm proxy
    os.environ["OPENAI_BASE_URL"] = "https://litellm.wenext.technology/v1"
    os.environ["COCOS_RAG_RERANK"] = "0" # Disable Rerank model since proxy key only has text-embedding-3-small
