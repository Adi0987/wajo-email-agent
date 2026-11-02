"""The one LLM client: any OpenAI-compatible chat API
(OpenAI, Anthropic, DeepSeek, Gemini, Groq, OpenRouter, Ollama...).

Configured in .env (see .env.example):
    LLM_API_KEY    your key
    LLM_BASE_URL   the provider's OpenAI-compatible endpoint
    LLM_MODEL      the model name

Every call asks for a JSON object. Providers that reject JSON mode or temperature 0 get a plain request instead,
and the JSON is read from the reply. Responses are cached: the eval keeps its cache in a file, an app session in
memory only. Standard library only.
"""

import hashlib
import http.client
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

DEFAULT_BASE_URL = "https://api.deepseek.com"  # what the saved eval results used
DEFAULT_MODEL = "deepseek-chat"


def load_env(path: str = ".env") -> None:
    if not Path(path).exists():
        return
    for line in Path(path).read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def settings() -> dict:
    load_env()
    return {
        "key": os.environ.get("LLM_API_KEY", ""),
        "base_url": os.environ.get("LLM_BASE_URL") or DEFAULT_BASE_URL,
        "model": os.environ.get("LLM_MODEL") or DEFAULT_MODEL,
    }


def parse_json(text: str) -> dict:
    """The JSON object in a reply, with or without code fences around it."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start : end + 1] if start >= 0 and end > start else text)


class LLM:
    def __init__(self, cache_path: Optional[str] = "eval/llm_cache.json"):
        self.config = settings()
        self.cache_path = Path(cache_path) if cache_path else None  # None: memory only, nothing on disk
        self.cache = json.loads(self.cache_path.read_text()) if self.cache_path and self.cache_path.exists() else {}
        self.lock = threading.Lock()
        self.plain = False  # set once the provider rejects JSON mode or temperature

    def complete_json(self, system: str, user: str) -> dict:
        key = hashlib.sha256(f"{self.config['model']}\n{system}\n{user}".encode()).hexdigest()
        if key not in self.cache:
            reply = self._call(system, user)
            with self.lock:
                self.cache[key] = reply
                if self.cache_path:
                    self.cache_path.write_text(json.dumps(self.cache, indent=1, sort_keys=True))
        return self.cache[key]

    def _call(self, system: str, user: str) -> dict:
        if not self.config["key"]:
            raise RuntimeError("No LLM_API_KEY: copy .env.example to .env and fill it in (see README).")
        if self.plain:  # no JSON mode to enforce it, so ask plainly
            system += "\n\nReply with only the JSON object: no other text, no code fences, no markup."
        body = {
            "model": self.config["model"],
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if self.plain:  # the settings every provider accepts, with room for models that think before answering
            body["max_completion_tokens"] = 16000
        else:
            body.update(max_tokens=2000, temperature=0, response_format={"type": "json_object"})
        try:
            content = self._post(body)
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:500]
            if error.code != 400 or self.plain:
                raise RuntimeError(f"The LLM provider returned {error.code}: {detail}") from error
            self.plain = True  # e.g. Anthropic: no JSON mode; reasoning models: no temperature or max_tokens
            return self._call(system, user)
        return parse_json(content)

    def _post(self, body: dict, attempts: int = 4) -> str:
        """Retries temporary failures (network errors, rate limits, server errors) with a growing wait."""
        for attempt in range(attempts):
            try:
                return self._post_once(body)
            except urllib.error.HTTPError as error:
                if error.code not in (429, 500, 502, 503, 504) or attempt == attempts - 1:
                    raise
            except (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError):
                if attempt == attempts - 1:
                    raise
            time.sleep(2**attempt)

    def _post_once(self, body: dict) -> str:
        request = urllib.request.Request(
            self.config["base_url"].rstrip("/") + "/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self.config['key']}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.load(response)["choices"][0]["message"]["content"]
