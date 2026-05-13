"""
ZENIC-AGENTS - Structural Pattern: Bridge

Decouples agent LLM usage from the concrete provider implementation.
Supports hot-swapping providers at runtime.

Designed for resource-constrained environments (Android/Termux, 500MB RAM).
"""

import logging
import threading
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ======================================================================
# Provider ABC
# ======================================================================

class LLMProvider(ABC):
    """
    Abstract base for LLM providers.

    Concrete providers implement:
      - complete(prompt, **kwargs) -> str
      - embed(text) -> List[float]
      - is_ready() -> bool
    """

    @abstractmethod
    def complete(self, prompt: str, **kwargs: Any) -> str:
        """Generate a completion for *prompt*."""
        ...

    @abstractmethod
    def embed(self, text: str) -> List[float]:
        """Generate an embedding vector for *text*."""
        ...

    @abstractmethod
    def is_ready(self) -> bool:
        """Return True if the provider is ready for requests."""
        ...


# ======================================================================
# Concrete providers
# ======================================================================

class LocalProvider(LLMProvider):
    """
    Provider backed by a local llama-cpp-python engine.

    Wraps any object that exposes:
      - ``generate(prompt, **kwargs) -> str``
      - ``embed(text) -> List[float]``   (optional)
      - ``is_loaded -> bool``
    """

    def __init__(self, engine: Any = None) -> None:
        self._engine = engine

    def complete(self, prompt: str, **kwargs: Any) -> str:
        if not self.is_ready():
            raise RuntimeError("LocalProvider: engine not loaded")
        try:
            result = self._engine.generate(prompt, **kwargs)
            return result if isinstance(result, str) else str(result)
        except AttributeError:
            # Fallback: try __call__ or _call_llm
            if hasattr(self._engine, "_call_llm"):
                result = self._engine._call_llm(prompt, **kwargs)
                return result if isinstance(result, str) else str(result)
            raise RuntimeError("LocalProvider: engine has no generate/_call_llm method")

    def embed(self, text: str) -> List[float]:
        if not self.is_ready():
            raise RuntimeError("LocalProvider: engine not loaded")
        if hasattr(self._engine, "embed"):
            return self._engine.embed(text)
        # Fallback: simple hash-based pseudo-embedding (deterministic)
        logger.warning("LocalProvider: engine has no embed(), using hash fallback")
        return self._pseudo_embed(text)

    def is_ready(self) -> bool:
        if self._engine is None:
            return False
        if hasattr(self._engine, "is_loaded"):
            return bool(self._engine.is_loaded)
        return True

    @staticmethod
    def _pseudo_embed(text: str, dim: int = 64) -> List[float]:
        """Deterministic hash-based pseudo-embedding (not for semantic use)."""
        import hashlib
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        vec = []
        for i in range(0, min(len(h), dim * 2), 2):
            vec.append(int(h[i:i + 2], 16) / 255.0)
        # Pad or truncate
        while len(vec) < dim:
            vec.append(0.0)
        return vec[:dim]


class RemoteProvider(LLMProvider):
    """
    Provider backed by an HTTP API (OpenAI-compatible).

    Uses only stdlib :mod:`urllib` — no external dependencies.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        api_key: str = "",
        model: str = "qwen3",
        embed_model: str = "",
        timeout: float = 120.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._embed_model = embed_model or model
        self._timeout = timeout
        self._ready: bool = True  # optimistic; checked on first call

    def complete(self, prompt: str, **kwargs: Any) -> str:
        import json
        import urllib.request
        import urllib.error

        url = f"{self._base_url}/chat/completions"
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        body = {
            "model": kwargs.pop("model", self._model),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 2048),
        }
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"]
        except Exception as exc:
            self._ready = False
            raise RuntimeError(f"RemoteProvider: request failed – {exc}") from exc

    def embed(self, text: str) -> List[float]:
        import json
        import urllib.request
        import urllib.error

        url = f"{self._base_url}/embeddings"
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        body = {"model": self._embed_model, "input": text}
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            return result["data"][0]["embedding"]
        except Exception as exc:
            logger.warning("RemoteProvider: embed failed – %s, using fallback", exc)
            return LocalProvider._pseudo_embed(text)

    def is_ready(self) -> bool:
        return self._ready


# ======================================================================
# Bridge
# ======================================================================

class AgentLLMBridge:
    """
    Bridge that decouples an agent from its LLM provider.

    Supports hot-swapping the provider at runtime so agents can switch
    between local and remote inference without restart.

    Usage::

        bridge = AgentLLMBridge(LocalProvider(engine))
        result = bridge.complete("Hello")
        bridge.switch_provider(RemoteProvider(url=...))
        result2 = bridge.complete("Hello again")
    """

    def __init__(self, provider: LLMProvider) -> None:
        if not isinstance(provider, LLMProvider):
            raise ValueError("AgentLLMBridge: provider must be an LLMProvider")
        self._provider = provider
        self._lock = threading.Lock()
        self._switch_count = 0

    # ------------------------------------------------------------------
    # Delegation
    # ------------------------------------------------------------------

    def complete(self, prompt: str, **kwargs: Any) -> str:
        """
        Generate a completion via the current provider.

        Args:
            prompt: Input text.
            **kwargs: Provider-specific options.

        Returns:
            Generated text.

        Raises:
            RuntimeError: If the current provider fails.
        """
        with self._lock:
            provider = self._provider
        return provider.complete(prompt, **kwargs)

    def embed(self, text: str) -> List[float]:
        """Generate an embedding via the current provider."""
        with self._lock:
            provider = self._provider
        return provider.embed(text)

    # ------------------------------------------------------------------
    # Hot-swap
    # ------------------------------------------------------------------

    def switch_provider(self, new_provider: LLMProvider) -> None:
        """
        Hot-swap the underlying provider.

        The switch is atomic — concurrent calls will see either the old
        or the new provider, never an inconsistent state.

        Args:
            new_provider: The replacement :class:`LLMProvider`.

        Raises:
            ValueError: If *new_provider* is not an LLMProvider.
        """
        if not isinstance(new_provider, LLMProvider):
            raise ValueError("AgentLLMBridge: new_provider must be an LLMProvider")
        with self._lock:
            old_name = type(self._provider).__name__
            self._provider = new_provider
            self._switch_count += 1
        logger.info(
            "AgentLLMBridge: switched provider %s → %s (switch #%d)",
            old_name,
            type(new_provider).__name__,
            self._switch_count,
        )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def current_provider(self) -> LLMProvider:
        """Return the currently active provider."""
        with self._lock:
            return self._provider

    @property
    def stats(self) -> Dict[str, Any]:
        """Return bridge statistics."""
        with self._lock:
            return {
                "provider": type(self._provider).__name__,
                "provider_ready": self._provider.is_ready(),
                "switch_count": self._switch_count,
            }
