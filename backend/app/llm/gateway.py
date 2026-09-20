# This file is a gateway for the LLM we will be using as our brain

from langchain_nvidia_ai_endpoints import ChatNVIDIA
from app.config import NVIDIA_API_KEY, NVIDIA_MODEL

llm = ChatNVIDIA(
    model=NVIDIA_MODEL,
    api_key=NVIDIA_API_KEY,
)