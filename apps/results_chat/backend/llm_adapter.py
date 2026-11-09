"""Server-side adapter to a conversational LLM.

Default path: a LOCAL llama.cpp server (llama-server, OpenAI-compatible
HTTP API) running on this same host, started by
apps/results_chat/run.sh alongside the Flask app. See
apps/results_chat/llm_runtime/MODEL_PROVENANCE.json for the exact model/
runtime this points at. After this local server is running, inference
works with no external API and no internet access.

This module never assumes credentials exist for a remote provider -- if
neither a local server is reachable nor remote credentials are
configured, `is_configured()` returns False and the caller must fall back
to the deterministic factual-answer path, clearly labeled, not silently
claim LLM output.

Provider resolution (RESULTS_CHAT_LLM_PROVIDER):
  - unset (default): auto-detect. Probes the local llama-server's
    /health endpoint (RESULTS_CHAT_LOCAL_LLM_URL, default
    http://127.0.0.1:8788); if it responds, provider="local". Otherwise
    provider="none" (factual mode).
  - "local": force the local llama-server path (same URL as above); does
    NOT silently fall back if the health probe fails -- is_configured()
    will report False and the caller handles the fallback.
  - "anthropic": Anthropic Messages API. Requires ANTHROPIC_API_KEY.
  - "openai_compatible": any other OpenAI-chat-completions-compatible
    HTTP endpoint (hosted or self-hosted). Requires LLM_API_BASE, LLM_MODEL.
  - "none": explicitly disabled.

Safety/design notes (unchanged from the previous version of this file):
  - The LLM is never given tool access, shell access, or any ability to
    act -- it is called with a single text-completion request and its
    reply is returned as plain text. It cannot execute anything.
  - For factual/grounded questions, the LLM is given only the already-
    retrieved evidence/knowledge-base snippet as its source of facts and
    is told to decline rather than invent when the snippet doesn't cover
    the question.
  - For chart requests, the LLM is asked to output ONLY a JSON object
    matching chart_engine.py's schema -- it never receives or produces
    raw plotted numbers; chart_engine.py always re-reads real evidence
    for the actual numbers (see chart_engine.py's module docstring).
  - No API key or model file path is ever returned to the browser.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Optional


class LLMError(Exception):
    pass


@dataclass
class LLMConfig:
    provider: str  # "local" | "anthropic" | "openai_compatible" | "none"
    model: Optional[str] = None
    api_base: Optional[str] = None
    api_key_present: bool = False
    timeout_seconds: float = 60.0
    local_url: str = field(default_factory=lambda: os.environ.get(
        "RESULTS_CHAT_LOCAL_LLM_URL", "http://127.0.0.1:8788"))


_HEALTH_CACHE: dict = {"checked_at": 0.0, "ok": False}
_HEALTH_TTL_SECONDS = 5.0


def _local_server_healthy(url: str) -> bool:
    now = time.time()
    if now - _HEALTH_CACHE["checked_at"] < _HEALTH_TTL_SECONDS:
        return _HEALTH_CACHE["ok"]
    ok = False
    try:
        req = urllib.request.Request(url.rstrip("/") + "/health", method="GET")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            ok = resp.status == 200
    except (urllib.error.URLError, OSError):
        ok = False
    _HEALTH_CACHE["checked_at"] = now
    _HEALTH_CACHE["ok"] = ok
    return ok


def load_config() -> LLMConfig:
    provider_env = os.environ.get("RESULTS_CHAT_LLM_PROVIDER", "").strip().lower()
    local_url = os.environ.get("RESULTS_CHAT_LOCAL_LLM_URL", "http://127.0.0.1:8788")

    if provider_env == "anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY")
        return LLMConfig(
            provider="anthropic",
            model=os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
            api_base=os.environ.get("ANTHROPIC_API_BASE", "https://api.anthropic.com"),
            api_key_present=bool(key),
        )
    if provider_env == "openai_compatible":
        key = os.environ.get("LLM_API_KEY")
        return LLMConfig(
            provider="openai_compatible",
            model=os.environ.get("LLM_MODEL"),
            api_base=os.environ.get("LLM_API_BASE"),
            api_key_present=bool(key),
        )
    if provider_env == "none":
        return LLMConfig(provider="none")
    if provider_env == "local":
        return LLMConfig(provider="local", model=os.environ.get("RESULTS_CHAT_LOCAL_LLM_MODEL", "local"),
                          api_base=local_url, local_url=local_url)

    # Unset: auto-detect the local server first (this is the path the
    # upgrade is meant to demonstrate by default), else fall back to none.
    if _local_server_healthy(local_url):
        return LLMConfig(provider="local", model=os.environ.get("RESULTS_CHAT_LOCAL_LLM_MODEL", "local"),
                          api_base=local_url, local_url=local_url)
    return LLMConfig(provider="none")


def is_configured(cfg: Optional[LLMConfig] = None) -> bool:
    cfg = cfg or load_config()
    if cfg.provider == "local":
        return _local_server_healthy(cfg.local_url)
    if cfg.provider == "anthropic":
        return cfg.api_key_present
    if cfg.provider == "openai_compatible":
        return bool(cfg.api_base and cfg.model)
    return False


def build_messages(system_prompt: str, history: list, user_message: str) -> list:
    """history: list of {"role": "user"|"assistant", "content": str},
    oldest first, already bounded by the caller (app.py)."""
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    return messages


def _post_json(url: str, headers: dict, payload: dict, timeout: float) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise LLMError(f"HTTP {exc.code} from LLM provider: {detail}") from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"could not reach LLM provider: {exc}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise LLMError(f"LLM provider returned a non-JSON response: {exc}") from exc


def generate(messages: list, cfg: Optional[LLMConfig] = None,
             max_tokens: int = 500, temperature: float = 0.2) -> str:
    """Call the configured LLM with a full chat message list. Raises
    LLMError on any failure -- callers must catch this and fall back to
    factual mode rather than erroring the whole request."""
    cfg = cfg or load_config()
    if not is_configured(cfg):
        raise LLMError(f"no LLM provider is available (provider={cfg.provider})")

    if cfg.provider == "local":
        url = cfg.api_base.rstrip("/") + "/v1/chat/completions"
        headers = {"content-type": "application/json"}
        payload = {
            "model": cfg.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        resp = _post_json(url, headers, payload, cfg.timeout_seconds)
        try:
            return resp["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"unexpected local-server response shape: {resp}") from exc

    if cfg.provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        url = cfg.api_base.rstrip("/") + "/v1/messages"
        headers = {
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        convo = [m for m in messages if m["role"] != "system"]
        payload = {"model": cfg.model, "max_tokens": max_tokens, "system": system, "messages": convo}
        resp = _post_json(url, headers, payload, cfg.timeout_seconds)
        try:
            blocks = resp["content"]
            return "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
        except (KeyError, TypeError) as exc:
            raise LLMError(f"unexpected Anthropic response shape: {resp}") from exc

    if cfg.provider == "openai_compatible":
        api_key = os.environ.get("LLM_API_KEY")
        url = cfg.api_base.rstrip("/") + "/chat/completions"
        headers = {"content-type": "application/json"}
        if api_key:
            headers["authorization"] = f"Bearer {api_key}"
        payload = {"model": cfg.model, "max_tokens": max_tokens, "temperature": temperature, "messages": messages}
        resp = _post_json(url, headers, payload, cfg.timeout_seconds)
        try:
            return resp["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"unexpected OpenAI-compatible response shape: {resp}") from exc

    raise LLMError(f"unknown provider: {cfg.provider}")
