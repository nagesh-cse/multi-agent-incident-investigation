"""
LLM Client Factory supporting Google Gemini (Free tier) with seamless
deterministic fallback for offline testing, grading, and CI.
"""
from __future__ import annotations
import os
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()


class LLMConfig:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        self.use_mock = os.getenv("USE_MOCK_LLM", "false").lower() in ("true", "1", "yes") or not self.api_key

    def get_chat_model(self):
        """Returns ChatGoogleGenerativeAI instance if API key is configured, else None."""
        if not self.use_mock and self.api_key:
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
                return ChatGoogleGenerativeAI(
                    model=self.model_name,
                    google_api_key=self.api_key,
                    temperature=0.1,
                )
            except Exception as e:
                print(f"[Warning] Failed to initialize Gemini LLM ({e}). Falling back to deterministic mode.")
                return None
        return None


llm_config = LLMConfig()
