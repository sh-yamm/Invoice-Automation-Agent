"""The LLM gateway: the only way any part of the agent talks to a model.

Every call is throttled to the free tier's rate limit and retried with backoff on transient errors
(3 tries per model). If a model stays down, the call moves to the next model in its fallback chain
(settings.fallback_vision / fallback_text). Replies can be served from a file cache (so demo samples
never need a live call), and every call is logged to the case record with the model that answered
and its reasoning trace. If every model fails, it raises AiUnavailable and the pipeline turns that
into a hold. It never approves on failure.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from pathlib import Path

import httpx
import jsonschema

BACKOFF = (1, 2)  # 3 tries per model, then the next model in the chain
TIMEOUT = 120.0
RETRY_STATUS = {429, 500, 502, 503, 504}


class AiUnavailable(RuntimeError):
    """A model could not be reached after retries (or rejected the request)."""


class RequestRejected(AiUnavailable):
    """The service refused the request itself (HTTP 400): another model would refuse it too."""


class InvalidModelOutput(ValueError):
    """The model's reply did not match the required JSON schema, even after one correction."""


def _safe(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", key)


def _extract_json(text: str | None):
    if not text:
        raise ValueError("empty reply")
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if fence:
        t = fence.group(1).strip()
    start = min([i for i in (t.find("{"), t.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("no JSON object in the reply")
    return json.JSONDecoder().raw_decode(t[start:])[0]


class Gateway:
    def __init__(self, settings, store=None, cache_dir: Path | None = None, *, clock=time.monotonic,
                 sleep=time.sleep, client: httpx.Client | None = None, offline: bool = False):
        self.s = settings
        self.offline = offline  # cache only: a miss raises instead of calling the network
        self.store = store
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.clock, self.sleep = clock, sleep
        self.client = client or httpx.Client(timeout=TIMEOUT)
        self.models = {"extract": settings.model_extract, "extract_text": settings.model_extract_text,
                       "fast": settings.model_fast, "agent": settings.model_agent,
                       "parse": settings.model_parse, "embed": settings.model_embed}
        self._interval = 60.0 / max(1, settings.llm_max_rpm)
        self._next_slot = 0.0
        self._lock = threading.Lock()
        self._embed_cache: dict[str, list[float]] = {}

    # ---------- plumbing ----------
    def _throttle(self) -> None:
        with self._lock:
            now = self.clock()
            wait = self._next_slot - now
            self._next_slot = max(now, self._next_slot) + self._interval
        if wait > 0:
            self.sleep(wait)

    def _post(self, url: str, **kwargs) -> dict:
        if self.offline:
            raise AiUnavailable("offline mode: no cached response for this call")
        headers = {"Authorization": f"Bearer {self.s.nvidia_api_key}", "Accept": "application/json"}
        last = ""
        for attempt in range(len(BACKOFF) + 1):
            self._throttle()
            try:
                r = self.client.post(url, headers=headers, **kwargs)
                if r.status_code in RETRY_STATUS:
                    last = f"HTTP {r.status_code}"
                elif r.status_code == 400:
                    raise RequestRejected(f"HTTP 400: {r.text[:200]}")
                elif r.status_code >= 400:  # e.g. 404: this model is not deployed; the next one may be
                    raise AiUnavailable(f"HTTP {r.status_code}: {r.text[:200]}")
                else:
                    return r.json()
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last = f"{type(e).__name__}: {e}"
            if attempt < len(BACKOFF):
                self.sleep(BACKOFF[attempt])
        raise AiUnavailable(f"no response after {len(BACKOFF) + 1} attempts ({last})")

    def _cache_path(self, key: str | None) -> Path | None:
        return self.cache_dir / f"{_safe(key)}.json" if key and self.cache_dir else None

    def _cached(self, key):
        p = self._cache_path(key)
        return json.loads(p.read_text(encoding="utf-8")) if p and p.exists() else None

    def _save(self, key, value) -> None:
        p = self._cache_path(key)
        if p:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")

    def _log(self, case_id, node, model, prompt, response, reasoning, started, tokens=None, cached=False):
        if self.store and case_id:
            self.store.add_llm_call(case_id, node, model + (" (cached)" if cached else ""), prompt, response,
                                    reasoning, int((self.clock() - started) * 1000), tokens)

    def chain(self, slot: str) -> list[str]:
        """The model for this kind of call, then its backups, in the order they are tried."""
        backups = self.s.fallback_vision if slot == "extract" else self.s.fallback_text
        return list(dict.fromkeys([self.models[slot], *backups]))

    def _chat(self, slot: str, messages: list, extra: dict) -> tuple[dict, str]:
        """One chat completion: each model in the chain gets its retries before the next one is tried.
        Returns the reply and the model that gave it."""
        failures = []
        for model in self.chain(slot):
            body = {"model": model, "messages": messages, "temperature": 0, "max_tokens": 8192, **extra}
            try:
                return self._post(f"{self.s.nvidia_base_url}/chat/completions", json=body), model
            except RequestRejected:
                raise
            except AiUnavailable as e:
                failures.append(f"{model}: {e}")
        raise AiUnavailable("every model failed (" + "; ".join(failures) + ")")

    # ---------- public calls ----------
    def parse_page(self, png: Path, *, case_id: str | None, cache_key: str | None = None) -> str:
        started = self.clock()
        cached = self._cached(cache_key)
        if cached is not None:
            self._log(case_id, "parse_pages", self.models["parse"], {"page": str(png)}, cached, None, started, cached=True)
            return cached["content"]
        files = {"document": (Path(png).name, Path(png).read_bytes(), "image/png"),
                 "options": (None, json.dumps({"decoding": {"max_output_tokens": 4096}}), "application/json")}
        data = self._post(self.s.parse_url, files=files)
        self._save(cache_key, data)
        self._log(case_id, "parse_pages", self.models["parse"], {"page": str(png)}, data, None, started,
                  (data.get("usage") or {}).get("output_tokens"))
        return data["content"]

    def chat_json(self, slot: str, messages: list, schema: dict, *, case_id: str | None, node: str,
                  cache_key: str | None = None) -> tuple[dict, str | None]:
        """A JSON answer validated against `schema`. One correction round if it doesn't validate."""
        started = self.clock()
        cached = self._cached(cache_key)
        if cached is not None:
            self._log(case_id, node, self.models[slot], messages, cached["data"], cached.get("reasoning"), started,
                      cached=True)
            return cached["data"], cached.get("reasoning")
        convo = list(messages)
        reasoning_parts = []
        for attempt in range(2):
            reply, model = self._chat(slot, convo, {})
            msg = reply["choices"][0]["message"]
            reasoning = msg.get("reasoning_content") or msg.get("reasoning")
            if reasoning:
                reasoning_parts.append(reasoning)
            content = msg.get("content") or ""
            try:
                data = _extract_json(content)
                jsonschema.validate(data, schema)
            except (ValueError, jsonschema.ValidationError) as e:
                err = e.message if isinstance(e, jsonschema.ValidationError) else str(e)
                self._log(case_id, node, model, convo, {"invalid": content[:2000], "error": err},
                          reasoning, started, (reply.get("usage") or {}).get("total_tokens"))
                if attempt == 0:
                    convo = convo + [{"role": "assistant", "content": content},
                                     {"role": "user", "content": f"Your reply did not match the required JSON "
                                                                 f"schema ({err}). Reply again with corrected JSON "
                                                                 f"only. Required keys: {schema.get('required', [])}."}]
                    continue
                raise InvalidModelOutput(err) from e
            joined = "\n\n".join(reasoning_parts) or None
            self._log(case_id, node, model, convo, data, joined, started,
                      (reply.get("usage") or {}).get("total_tokens"))
            self._save(cache_key, {"data": data, "reasoning": joined})
            return data, joined
        raise InvalidModelOutput("unreachable")

    def chat_tools(self, slot: str, messages: list, tools: list, *, case_id: str | None, node: str,
                   cache_key: str | None = None) -> dict:
        """One assistant turn with tools available. Returns the assistant message (may contain tool_calls)."""
        started = self.clock()
        cached = self._cached(cache_key)
        if cached is not None:
            self._log(case_id, node, self.models[slot], messages, cached, cached.get("reasoning_content"), started,
                      cached=True)
            return cached
        reply, model = self._chat(slot, messages, {"tools": tools, "tool_choice": "auto"})
        msg = reply["choices"][0]["message"]
        self._save(cache_key, msg)
        self._log(case_id, node, model, messages, msg,
                  msg.get("reasoning_content") or msg.get("reasoning"), started,
                  (reply.get("usage") or {}).get("total_tokens"))
        return msg

    def embed(self, texts: list[str], *, input_type: str = "query") -> list[list[float]]:
        """Embeddings, cached in memory per text (not logged per case: they are lookups, not decisions)."""
        key = lambda t: hashlib.sha1(f"{input_type}|{t}".encode()).hexdigest()
        missing = list(dict.fromkeys(t for t in texts if key(t) not in self._embed_cache))
        for t in missing:  # one text per request: the endpoint fails on batches (HTTP 500)
            data = self._post(f"{self.s.nvidia_base_url}/embeddings",
                              json={"model": self.models["embed"], "input": [t], "input_type": input_type,
                                    "encoding_format": "float"})
            self._embed_cache[key(t)] = data["data"][0]["embedding"]
        return [self._embed_cache[key(t)] for t in texts]
