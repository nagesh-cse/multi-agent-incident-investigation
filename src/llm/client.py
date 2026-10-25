"""
LLM Client Factory supporting OpenRouter (Free tier models) and Google Gemini,
with seamless deterministic fallback for offline testing and CI.
"""
from __future__ import annotations
import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


class LLMConfig:
    def __init__(self):
        # OpenRouter support
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        self.openrouter_model = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
        
        # Gemini support
        self.gemini_api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

        # Timeout and Retry configuration
        self.timeout = int(os.getenv("LLM_TIMEOUT", "20"))
        self.max_retries = int(os.getenv("LLM_MAX_RETRIES", "2"))

        # Explicit mock override
        self.force_mock = os.getenv("USE_MOCK_LLM", "false").lower() in ("true", "1", "yes")

    def get_chat_model(self):
        """
        Returns a Chat model instance:
        1. OpenRouter (if OPENROUTER_API_KEY is set)
        2. Gemini (if GEMINI_API_KEY is set)
        3. None (deterministic offline mode)
        """
        if self.force_mock:
            return None

        # Priority 1: OpenRouter
        if self.openrouter_api_key:
            try:
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(
                    model=self.openrouter_model,
                    openai_api_key=self.openrouter_api_key,
                    openai_api_base="https://openrouter.ai/api/v1",
                    temperature=0.1,
                    timeout=self.timeout,
                    max_retries=self.max_retries,
                )
            except Exception as e:
                print(f"[LLM Warning] OpenRouter init failed: {e}")

        # Priority 2: Gemini
        if self.gemini_api_key:
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
                return ChatGoogleGenerativeAI(
                    model=self.gemini_model,
                    google_api_key=self.gemini_api_key,
                    temperature=0.1,
                )
            except Exception as e:
                print(f"[LLM Warning] Gemini init failed: {e}")

        return None


llm_config = LLMConfig()
