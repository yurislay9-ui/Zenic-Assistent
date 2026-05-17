"""
MiniAIEngine model lifecycle mixin: load_model, unload_model, stats, _call_llm, _extract_answer.
"""

import re
import time
import threading
import concurrent.futures
from typing import Optional, Dict, Any

from ._imports import (
    MODEL_PATH, N_CTX, N_THREADS, TEMPERATURE, LLM_TIMEOUT_S, logger,
)


class ModelLifecycleMixin:
    """Model lifecycle and LLM call helper methods."""

    def _init_lifecycle(self, model_path: Optional[str] = None, auto_load: bool = True):
        self._llm = None
        self._model_path = model_path or MODEL_PATH
        self._loaded = False
        self._load_time = 0.0
        self._call_count = 0
        self._fallback_count = 0
        self._total_llm_time = 0.0
        self._lock = threading.Lock()
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

        if auto_load:
            self.load_model()

    # ================================================================
    #  MODEL LIFECYCLE
    # ================================================================

    def load_model(self) -> bool:
        """Carga el modelo GGUF con llama-cpp-python. Returns True if loaded."""
        import os

        if self._loaded and self._llm is not None:
            return True

        if not os.path.exists(self._model_path):
            logger.warning(f"Model not found: {self._model_path}. MiniAI will use fallbacks only.")
            return False

        try:
            from llama_cpp import Llama  # type: ignore[import-unresolved]
            start = time.time()
            self._llm = Llama(
                model_path=self._model_path,
                n_ctx=N_CTX,
                n_threads=N_THREADS,
                n_batch=int(os.environ.get("ZENIC_LLM_BATCH", "512")),
                use_mmap=True,
                use_mlock=True,  # ARM: lock model in RAM, prevent page faults during inference
                verbose=False,
            )
            self._load_time = time.time() - start
            self._loaded = True
            logger.info(f"MiniAI: Qwen3-0.6B loaded in {self._load_time:.1f}s (n_ctx={N_CTX}, n_threads={N_THREADS}, n_batch={os.environ.get('ZENIC_LLM_BATCH', '512')})")
            # Warm-up inference: first call is 2-5x slower (KV cache init, buffer allocation).
            # Doing it here means the first real request won't timeout.
            self._warm_up()
            return True
        except ImportError:
            logger.warning("MiniAI: llama-cpp-python not installed. Using fallbacks only.")
            return False
        except Exception as e:
            logger.warning(f"MiniAI: Failed to load model: {e}. Using fallbacks only.")
            self._llm = None
            return False

    def _warm_up(self) -> None:
        """Run a dummy inference after model load to initialize KV cache and buffers.

        The first llama_cpp create_chat_completion() call is 2-5x slower because:
        - KV cache allocation and initialization
        - Batch processing buffer allocation
        - CPU cache warming for model weights
        Without warm-up, the first real request often exceeds LLM_TIMEOUT_S.
        """
        if not self._loaded or self._llm is None:
            return
        try:
            import time as _t
            t0 = _t.time()
            _ = self._llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": "You are helpful."},
                    {"role": "user", "content": "Say OK."},
                ],
                max_tokens=5,
                temperature=0.0,
            )
            elapsed = _t.time() - t0
            logger.info(f"MiniAI: Warm-up inference completed in {elapsed:.1f}s")
        except Exception as e:
            logger.warning(f"MiniAI: Warm-up inference failed (non-critical): {e}")

    def unload_model(self) -> None:
        """Libera el modelo de memoria (thread-safe)."""
        with self._lock:
            if self._llm is not None:
                del self._llm
                self._llm = None
                self._loaded = False
                if self._executor is not None:
                    self._executor.shutdown(wait=False)
                    self._executor = None  # Lazy re-creation on next use
                # Also shut down the verdict executor to prevent thread leak
                if hasattr(self, '_verdict_executor') and self._verdict_executor is not None:
                    self._verdict_executor.shutdown(wait=False)
                    self._verdict_executor = None
                logger.info("MiniAI: Model unloaded from memory")

    def chat(self, message: str, max_tokens: int = 256) -> Optional[str]:
        """Conversational LLM call for chat mode responses.

        Simple wrapper around _call_llm that uses a conversational system prompt.
        Returns the LLM response text, or None if model is not loaded / fails.
        """
        return self._call_llm(
            system_prompt="You are a helpful AI assistant. Respond concisely and directly.",
            user_prompt=message,
            max_tokens=max_tokens,
        )

    @property
    def is_loaded(self) -> bool:
        return self._loaded and self._llm is not None

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadísticas de uso del motor."""
        return {
            "model_loaded": self.is_loaded,
            "load_time_s": self._load_time,
            "total_calls": self._call_count,
            "fallback_calls": self._fallback_count,
            "llm_calls": self._call_count - self._fallback_count,
            "fallback_rate": self._fallback_count / max(self._call_count, 1),
            "avg_llm_time_s": self._total_llm_time / max(self._call_count - self._fallback_count, 1),
        }

    # ================================================================
    #  INTERNAL: LLM CALL HELPER
    # ================================================================

    def _call_llm(self, system_prompt: str, user_prompt: str, max_tokens: int) -> Optional[str]:
        """
        Llama al LLM con timeout enforcement y manejo de errores.
        Returns raw response text or None on failure.
        """
        if not self.is_loaded:
            return None

        with self._lock:
            self._call_count += 1
        start = time.time()

        def _actual_llm_call():
            """Inner function to submit to the executor with timeout."""
            return self._llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt + "\n/no_think"},  # /no_think disables Qwen3 thinking mode (saves 50-100 tokens on ARM)
                ],
                max_tokens=max_tokens,
                temperature=TEMPERATURE,
            )

        try:
            # Lazy executor creation (set to None after unload_model)
            if self._executor is None:
                self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = self._executor.submit(_actual_llm_call)
            try:
                response = future.result(timeout=LLM_TIMEOUT_S)
            except concurrent.futures.TimeoutError:
                future.cancel()
                logger.warning(f"MiniAI: LLM call timed out after {LLM_TIMEOUT_S}s for: {user_prompt[:50]}")
                # CRITICAL FIX: Recreate executor to unblock thread pool.
                # When a call times out, the underlying llama_cpp thread keeps running
                # and holds the executor's single worker (max_workers=1). All subsequent
                # calls are blocked until that thread finishes naturally, causing cascading
                # timeouts. By shutting down and recreating, we get a fresh thread.
                try:
                    self._executor.shutdown(wait=False)
                except Exception:
                    pass
                self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                with self._lock:
                    self._fallback_count += 1
                return None

            raw = response["choices"][0]["message"]["content"]
            answer = self._extract_answer(raw)
            elapsed = time.time() - start
            with self._lock:
                self._total_llm_time += elapsed

            if elapsed > LLM_TIMEOUT_S:
                logger.warning(f"MiniAI: Slow call ({elapsed:.1f}s) for: {user_prompt[:50]}")

            return answer

        except Exception as e:
            elapsed = time.time() - start
            logger.warning(f"MiniAI: LLM call failed ({elapsed:.1f}s): {e}")
            with self._lock:
                self._fallback_count += 1
            return None

    @staticmethod
    def _extract_answer(text: str) -> str:
        """Extrae la respuesta limpia del output de Qwen3 (maneja thinking mode)."""
        # Qwen3 outputs <think...</think then the answer
        match = re.search(r'</think\s*>(.*)', text, re.DOTALL)
        if match:
            answer = match.group(1).strip()
        else:
            # No think block - try to get last meaningful line
            lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
            answer = lines[-1] if lines else text.strip()

        # Clean markdown fences
        answer = re.sub(r'```(?:json|python)?\s*', '', answer)
        answer = re.sub(r'\s*```', '', answer)
        return answer.strip()
