"""
Live Token Tracking Module.
Captures real-time token usage from live LLM responses (OpenRouter / Gemini / OpenAI)
via LangChain callback handlers, with dynamic text-based estimation fallback.
"""
from __future__ import annotations
from typing import Any, Dict, Optional
from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.outputs import LLMResult


def estimate_tokens(text: str) -> int:
    """
    Dynamically estimates token count from raw text based on standard subword tokenization (~4 chars/token).
    Used for telemetry tool payloads and fallback offline estimation.
    """
    if not text:
        return 0
    # Standard rule of thumb: ~4 characters per token in English / JSON / Code
    return max(1, (len(text) + 3) // 4)


class LiveTokenTracker(BaseCallbackHandler):
    """
    LangChain callback handler that extracts live token usage directly
    from LLM API responses (OpenRouter, Google Gemini, OpenAI).
    """
    def __init__(self):
        super().__init__()
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.total_tokens: int = 0

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Invoked when LLM finishes generating."""
        # 1. Check response.llm_output['token_usage'] (OpenAI / OpenRouter standard)
        if response.llm_output and "token_usage" in response.llm_output:
            usage = response.llm_output["token_usage"]
            prompt = usage.get("prompt_tokens", 0)
            comp = usage.get("completion_tokens", 0)
            tot = usage.get("total_tokens", prompt + comp)
            if tot > 0:
                self.prompt_tokens += prompt
                self.completion_tokens += comp
                self.total_tokens += tot
                return

        # 2. Check message metadata (usage_metadata or response_metadata)
        for gen_list in response.generations:
            for gen in gen_list:
                msg = getattr(gen, "message", None)
                if msg is not None:
                    # LangChain standard usage_metadata
                    usage_meta = getattr(msg, "usage_metadata", None)
                    if usage_meta:
                        prompt = usage_meta.get("input_tokens", 0)
                        comp = usage_meta.get("output_tokens", 0)
                        tot = usage_meta.get("total_tokens", prompt + comp)
                        if tot > 0:
                            self.prompt_tokens += prompt
                            self.completion_tokens += comp
                            self.total_tokens += tot
                            return

                    # ChatGoogleGenerativeAI / OpenRouter response_metadata
                    resp_meta = getattr(msg, "response_metadata", {})
                    token_usage = resp_meta.get("token_usage") or resp_meta.get("usage_metadata")
                    if isinstance(token_usage, dict):
                        prompt = token_usage.get("prompt_tokens") or token_usage.get("input_tokens", 0)
                        comp = token_usage.get("completion_tokens") or token_usage.get("output_tokens", 0)
                        tot = token_usage.get("total_tokens", prompt + comp)
                        if tot > 0:
                            self.prompt_tokens += prompt
                            self.completion_tokens += comp
                            self.total_tokens += tot
                            return

        # 3. Fallback: Estimate from generated text if provider did not return usage numbers
        for gen_list in response.generations:
            for gen in gen_list:
                text = getattr(gen, "text", "") or (getattr(getattr(gen, "message", None), "content", "") if hasattr(gen, "message") else "")
                if text:
                    self.completion_tokens += estimate_tokens(str(text))
        if self.total_tokens == 0:
            self.total_tokens = self.prompt_tokens + self.completion_tokens
