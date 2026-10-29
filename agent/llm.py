"""DeepSeek chat client with a response cache. Standard library only.

Cached responses make eval runs repeatable and free after the first run.
"""
import hashlib
import json
import os
import threading
import urllib.request
from pathlib import Path

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"


def load_env(path: str = ".env") -> None:
    if not Path(path).exists():
        return
    for line in Path(path).read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


class LLM:
    def __init__(self, cache_path: str = "eval/llm_cache.json"):
        self.cache_path = Path(cache_path)
        self.cache = json.loads(self.cache_path.read_text()) if self.cache_path.exists() else {}
        self.lock = threading.Lock()

    def complete_json(self, system: str, user: str) -> dict:
        key = hashlib.sha256(f"{MODEL}\n{system}\n{user}".encode()).hexdigest()
        if key not in self.cache:
            reply = self._call(system, user)
            with self.lock:
                self.cache[key] = reply
                self.cache_path.write_text(json.dumps(self.cache, indent=1, sort_keys=True))
        return self.cache[key]

    def _call(self, system: str, user: str) -> dict:
        load_env()
        request = urllib.request.Request(
            API_URL,
            data=json.dumps({
                "model": MODEL,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
            }).encode(),
            headers={"Authorization": f"Bearer {os.environ['LLM_API_KEY']}",
                     "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            content = json.load(response)["choices"][0]["message"]["content"]
        return json.loads(content)
