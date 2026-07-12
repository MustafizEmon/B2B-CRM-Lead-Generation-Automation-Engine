from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_groq import ChatGroq

from app.config import settings

logger = logging.getLogger("crm_ai.llm")


class TracingCallbackHandler(BaseCallbackHandler):
    """Minimal LangChain callback handler used purely for observability/logging."""

    def on_llm_start(self, serialized, prompts, **kwargs):
        logger.debug("LLM call started (%d prompt chunk(s)).", len(prompts))

    def on_llm_end(self, response, **kwargs):
        logger.debug("LLM call finished.")

    def on_llm_error(self, error, **kwargs):
        logger.error("LLM call errored: %s", error)


def build_llm() -> ChatGroq:
    return ChatGroq(
        api_key=settings.groq_api_key or "unset",
        model=settings.model_name,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
        callbacks=[TracingCallbackHandler()],
    )


llm = build_llm()

_PROMPT_CACHE: Dict[str, Any] = {}
_TOKEN_LOG: List[tuple] = []  # rolling 60s window of (timestamp, estimated_tokens)

_RETRY_AFTER_RE = re.compile(r"try again in ([\d.]+)s", re.IGNORECASE)


def _cache_key(chain_name: str, payload: Dict[str, Any]) -> str:
    return f"{chain_name}::{json.dumps(payload, sort_keys=True, default=str)}"


def _tpm_budget() -> int:
    return int(settings.tpm_limit * settings.tpm_safety_margin)


def _wait_for_token_budget(estimated_tokens: int) -> None:
    while True:
        now = time.time()
        _TOKEN_LOG[:] = [(t, n) for t, n in _TOKEN_LOG if now - t < 60]
        used = sum(n for _, n in _TOKEN_LOG)
        budget = _tpm_budget()
        if used + estimated_tokens <= budget:
            _TOKEN_LOG.append((now, estimated_tokens))
            return
        oldest_t = _TOKEN_LOG[0][0] if _TOKEN_LOG else now
        sleep_for = max(0.5, 60 - (now - oldest_t))
        logger.info("Nearing TPM budget (%d/%d used); waiting %.1fs for headroom.", used, budget, sleep_for)
        time.sleep(sleep_for)


def _extract_retry_after(exc: Exception) -> Optional[float]:
    match = _RETRY_AFTER_RE.search(str(exc))
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def invoke_with_resilience(
    chain_name: str,
    runnable,
    payload: Dict[str, Any],
    max_tokens_estimate: Optional[int] = None,
) -> Any:
    """Invoke any Runnable with caching, TPM-aware throttling, retries+backoff, and timing.

    max_tokens_estimate should roughly match the max_tokens the chain's LLM is bound
    to (settings.max_tokens if unbound); used purely for proactive TPM budgeting.
    """
    if not settings.is_llm_configured:
        raise RuntimeError(
            "GROQ_API_KEY is not configured. Set it in your environment / .env file "
            "before running a campaign."
        )

    key = _cache_key(chain_name, payload)
    if settings.cache_enabled and key in _PROMPT_CACHE:
        logger.debug("[%s] cache hit.", chain_name)
        return _PROMPT_CACHE[key]

    estimated_tokens = max_tokens_estimate or settings.max_tokens

    last_exc: Optional[Exception] = None
    for attempt in range(1, settings.retry_count + 1):
        _wait_for_token_budget(estimated_tokens)
        start = time.time()
        try:
            time.sleep(settings.rate_limit_delay)
            result = runnable.invoke(payload)
            elapsed = time.time() - start
            logger.info("[%s] attempt %d succeeded in %.2fs.", chain_name, attempt, elapsed)
            if settings.cache_enabled:
                _PROMPT_CACHE[key] = result
            return result
        except Exception as exc:  # noqa: BLE001 - intentional resilience boundary
            last_exc = exc
            retry_after = _extract_retry_after(exc)
            wait = (retry_after + 0.5) if retry_after is not None else settings.backoff_base ** attempt
            logger.warning("[%s] attempt %d failed (%s). Retrying in %.1fs...", chain_name, attempt, exc, wait)
            time.sleep(wait)

    logger.error("[%s] all %d attempts failed. Last error: %s", chain_name, settings.retry_count, last_exc)
    raise RuntimeError(f"Chain '{chain_name}' failed after {settings.retry_count} attempts: {last_exc}")


def clear_cache() -> None:
    _PROMPT_CACHE.clear()




"""Note:
Shared Groq LLM client + resilience layer.

Ports `invoke_with_resilience()` from the notebook(for purpose of initial research) essentially 
unchanged: 
it adds an in-memory prompt cache, TPM (tokens-per-minute) self-throttling, and
retry-with-backoff (using the server's own "try again in Ns" hint when Groq
provides one, falling back to exponential backoff otherwise).

One client is built at import time from `app.config.settings` and reused by
every chain module -- mirroring the single shared `llm` in the notebook.
"""