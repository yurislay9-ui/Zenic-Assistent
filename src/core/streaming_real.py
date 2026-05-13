"""
StreamingReal — Token-by-token SSE streaming from llama_cpp.

Problem: The current system returns full responses at once. Users wait
for the entire generation to complete before seeing any output, which
feels slow even for short responses.

Solution: StreamingReal hooks into llama_cpp's built-in streaming API
to emit tokens one by one via Server-Sent Events (SSE). This provides:
  1. Immediate feedback to the user
  2. Progressive response display
  3. Cancellation support (stop mid-generation)

M8 Implementation: Uses llama_cpp's create_chat_completion with stream=True.
Works with Qwen3-0.6B on Termux/Android. No external APIs needed.
"""

import time
import json
import logging
from typing import Any, Dict, Generator, Optional, Callable

logger = logging.getLogger(__name__)

# SSE format constants
SSE_PREFIX = "data: "
SSE_DONE = "data: [DONE]\n\n"


class StreamingReal:
    """Token-by-token SSE streaming from local llama_cpp model."""

    def __init__(self, llm_engine=None):
        """
        Args:
            llm_engine: MiniAIEngine instance with loaded llama_cpp model
        """
        self._llm = llm_engine

    # ================================================================
    #  PUBLIC API
    # ================================================================

    def stream_chat(self, messages: list, max_tokens: int = 512,
                     temperature: float = 0.7,
                     on_token: Optional[Callable] = None) -> Generator[str, None, None]:
        """Stream a chat completion token by token.

        Args:
            messages: List of message dicts [{"role": "user", "content": "..."}]
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            on_token: Optional callback for each token

        Yields:
            SSE-formatted strings: "data: {...}\\n\\n"
        """
        if not self._llm or not self._llm.is_loaded:
            yield self._format_sse({"error": "LLM not loaded"}, event="error")
            return

        # Get the underlying llama_cpp model
        llama_model = getattr(self._llm, '_llm', None)
        if not llama_model:
            yield self._format_sse({"error": "Llama model not available"}, event="error")
            return

        # Prepare the prompt
        system_prompt = ""
        user_prompt = ""
        for msg in messages:
            if msg.get("role") == "system":
                system_prompt = msg.get("content", "")
            elif msg.get("role") == "user":
                user_prompt = msg.get("content", "")

        # Append /no_think for Qwen3
        user_prompt = user_prompt.rstrip() + "\n/no_think"

        try:
            # Use llama_cpp's streaming API
            start_time = time.time()
            token_count = 0

            # Try streaming completion
            try:
                stream = llama_model.create_chat_completion(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=True,
                )

                for chunk in stream:
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    token = delta.get("content", "")

                    if token:
                        token_count += 1
                        sse_data = {
                            "token": token,
                            "token_count": token_count,
                        }
                        yield self._format_sse(sse_data, event="token")

                        if on_token:
                            on_token(token)

                    # Check finish reason
                    finish = chunk.get("choices", [{}])[0].get("finish_reason")
                    if finish:
                        elapsed = time.time() - start_time
                        yield self._format_sse({
                            "finish_reason": finish,
                            "token_count": token_count,
                            "elapsed_s": round(elapsed, 2),
                            "tokens_per_second": round(token_count / max(elapsed, 0.01), 1),
                        }, event="done")

            except TypeError:
                # llama_cpp doesn't support stream=True, fallback to manual streaming
                logger.info("StreamingReal: stream not supported, using manual streaming")
                yield from self._manual_stream(
                    llama_model, messages, max_tokens, temperature, on_token
                )

        except Exception as e:
            logger.error(f"StreamingReal: Error during streaming: {e}")
            yield self._format_sse({"error": str(e)}, event="error")

        # Send [DONE] marker
        yield SSE_DONE

    def stream_code(self, task_description: str, language: str = "python",
                     max_tokens: int = 256) -> Generator[str, None, None]:
        """Stream code generation token by token.

        Args:
            task_description: What code to generate
            language: Target language
            max_tokens: Maximum tokens to generate

        Yields:
            SSE-formatted strings with code tokens
        """
        messages = [
            {
                "role": "system",
                "content": (
                    f"You are a code generator. Output ONLY {language} code. "
                    f"No explanations. No markdown fences. Just the code."
                ),
            },
            {
                "role": "user",
                "content": f"Generate {language} code for: {task_description}",
            },
        ]

        yield from self.stream_chat(messages, max_tokens=max_tokens, temperature=0.3)

    def stream_to_fastapi(self, messages: list, max_tokens: int = 512):
        """Create a FastAPI StreamingResponse-compatible generator.

        Usage in FastAPI:
            from fastapi.responses import StreamingResponse
            streamer = StreamingReal(orchestrator._ai)
            return StreamingResponse(
                streamer.stream_to_fastapi(messages),
                media_type="text/event-stream"
            )
        """
        for sse_chunk in self.stream_chat(messages, max_tokens):
            yield sse_chunk

    # ================================================================
    #  HELPERS
    # ================================================================

    def _manual_stream(self, llama_model, messages: list,
                        max_tokens: int, temperature: float,
                        on_token: Optional[Callable] = None) -> Generator[str, None, None]:
        """Manual streaming by generating small chunks sequentially.

        Fallback when llama_cpp doesn't support stream=True.
        Generates max_tokens in small batches for progressive output.
        """
        batch_size = 20  # tokens per batch
        total_generated = 0
        start_time = time.time()

        while total_generated < max_tokens:
            remaining = max_tokens - total_generated
            this_batch = min(batch_size, remaining)

            try:
                result = llama_model.create_chat_completion(
                    messages=messages,
                    max_tokens=this_batch,
                    temperature=temperature,
                    stream=False,
                )

                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not content:
                    break

                # Emit as a batch token
                total_generated += this_batch
                elapsed = time.time() - start_time

                yield self._format_sse({
                    "token": content,
                    "token_count": total_generated,
                    "batch": True,
                }, event="token")

                if on_token:
                    on_token(content)

                # Add to conversation for context continuity
                # (helps with coherence across batches)
                messages.append({"role": "assistant", "content": content})

            except Exception as e:
                logger.error(f"Manual stream batch error: {e}")
                break

        # Done
        elapsed = time.time() - start_time
        yield self._format_sse({
            "finish_reason": "stop",
            "token_count": total_generated,
            "elapsed_s": round(elapsed, 2),
            "batch_mode": True,
        }, event="done")

    @staticmethod
    def _format_sse(data: Dict, event: str = "") -> str:
        """Format a dict as an SSE message."""
        payload = json.dumps(data, ensure_ascii=False)
        if event:
            return f"event: {event}\n{SSE_PREFIX}{payload}\n\n"
        return f"{SSE_PREFIX}{payload}\n\n"
