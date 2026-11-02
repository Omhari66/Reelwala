"""Abstract LLM client interface, Gemini REST implementation, and testing fakes."""

import base64
import json
import logging
import mimetypes
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMClient(ABC):
    """Abstract interface for LLM calls with structured outputs."""

    @abstractmethod
    def generate_json(
        self,
        prompt: str,
        schema: type[T],
        images: list[str] | None = None,
        system_instruction: str | None = None,
    ) -> T:
        """Generate structured JSON conforming to a Pydantic schema."""
        raise NotImplementedError


class GeminiClient(LLMClient):
    """Live Google Gemini API client using standard HTTP REST interface."""

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash") -> None:
        self.api_key = api_key
        self.model = model
        self.endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"

    def generate_json(
        self,
        prompt: str,
        schema: type[T],
        images: list[str] | None = None,
        system_instruction: str | None = None,
    ) -> T:
        """Execute structured JSON generation request against Gemini REST API."""
        parts: list[dict[str, Any]] = [{"text": prompt}]

        if images:
            for img_path in images:
                p = Path(img_path)
                if p.is_file():
                    mime, _ = mimetypes.guess_type(str(p))
                    mime = mime or "image/jpeg"
                    data_b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
                    parts.append({"inline_data": {"mime_type": mime, "data": data_b64}})

        contents = [{"parts": parts}]
        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.2,
            },
        }

        if system_instruction:
            body["system_instruction"] = {"parts": [{"text": system_instruction}]}

        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                self.endpoint,
                params={"key": self.api_key},
                json=body,
            )
            resp.raise_for_status()
            resp_data = resp.json()

        try:
            candidates = resp_data.get("candidates", [])
            if not candidates:
                raise ValueError(f"No candidates returned by Gemini: {resp_data}")

            first_candidate = candidates[0]
            text = first_candidate["content"]["parts"][0]["text"]
            # Clean markdown codeblocks if returned
            clean_text = text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            if clean_text.startswith("```"):
                clean_text = clean_text[3:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]

            parsed_json = json.loads(clean_text.strip())
            return schema.model_validate(parsed_json)
        except Exception as e:
            logger.error(f"Failed to parse Gemini response as {schema.__name__}: {e}", exc_info=True)
            raise


class FakeLLMClient(LLMClient):
    """Test fake returning canned responses conforming to the requested schema."""

    def __init__(
        self,
        canned_responses: dict[Any, Any] | list[Any] | Callable[[str, type[Any]], Any] | None = None,
    ) -> None:
        self.canned_responses = canned_responses or {}
        self.call_history: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def set_response(self, schema_or_key: Any, response: Any) -> None:
        """Set or update canned response for a given schema or key."""
        with self._lock:
            if isinstance(self.canned_responses, dict):
                self.canned_responses[schema_or_key] = response

    def generate_json(
        self,
        prompt: str,
        schema: type[T],
        images: list[str] | None = None,
        system_instruction: str | None = None,
    ) -> T:
        """Return matching canned response parsed as requested schema."""
        with self._lock:
            self.call_history.append(
                {
                    "prompt": prompt,
                    "schema": schema,
                    "images": images,
                    "system_instruction": system_instruction,
                }
            )

            raw: Any = None
            if callable(self.canned_responses):
                raw = self.canned_responses(prompt, schema)
            elif isinstance(self.canned_responses, list) and self.canned_responses:
                raw = self.canned_responses.pop(0)
            elif isinstance(self.canned_responses, dict):
                if schema in self.canned_responses:
                    raw = self.canned_responses[schema]
                elif schema.__name__ in self.canned_responses:
                    raw = self.canned_responses[schema.__name__]
                elif "default" in self.canned_responses:
                    raw = self.canned_responses["default"]

        if raw is None:
            raise ValueError(f"No canned response provided for schema {schema.__name__}")

        if isinstance(raw, schema):
            return raw
        if isinstance(raw, dict):
            return schema.model_validate(raw)
        if isinstance(raw, str):
            return schema.model_validate_json(raw)

        return schema.model_validate(raw)


def get_llm_client() -> LLMClient:
    """Return configured LLM client (live Gemini or FakeLLMClient)."""
    from app.config import settings

    if settings.LLM_PROVIDER == "gemini" and settings.LLM_API_KEY:
        model = settings.LLM_MODEL_TEXT or "gemini-1.5-flash"
        return GeminiClient(api_key=settings.LLM_API_KEY, model=model)

    return FakeLLMClient()
