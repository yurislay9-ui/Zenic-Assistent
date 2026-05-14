"""PostMixin - Additional methods."""

import json

from ._shared import logger, _run_async


class PostMixinExtraMixin:
    """Additional methods."""

    def _handle_think(self):
        """POST /v1/think - Razonar con ThinkingEngine."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"error": f"Invalid JSON: {e}"}, status=400)
            return
        query = data.get("query", "")
        if not query:
            self._send_json({"error": "Missing 'query' field"}, status=400)
            return
        context = data.get("context", "")
        try:
            result = _run_async(self.orchestrator.think(query, context))
            if result is None:
                result = {"error": "Orchestrator returned empty result"}
            self._send_json(result)
        except Exception as e:
            logger.error(f"Thinking error: {e}", exc_info=True)
            self._send_json({"error": str(e)}, status=500)
    def _handle_reason(self):
        """POST /v1/reason - Razonamiento avanzado (Phase 8)."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"error": f"Invalid JSON: {e}"}, status=400)
            return
        query = data.get("query", "")
        if not query:
            self._send_json({"error": "Missing 'query' field"}, status=400)
            return
        mode = data.get("mode", "auto")
        context = data.get("context", "")
        try:
            result = _run_async(self.orchestrator.reason(query, mode, context))
            if result is None:
                result = {"error": "Orchestrator returned empty result"}
            self._send_json(result)
        except Exception as e:
            logger.error(f"Reasoning error: {e}", exc_info=True)
            self._send_json({"error": str(e)}, status=500)
    def _handle_chain_validate(self):
        """POST /v1/chain/validate - Validar cadena de logica."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"error": f"Invalid JSON: {e}"}, status=400)
            return
        description = data.get("description", "")
        if not description:
            self._send_json({"error": "Missing 'description' field"}, status=400)
            return
        try:
            result = _run_async(self.orchestrator.validate_logic_chain(description))
            if result is None:
                result = {"error": "Orchestrator returned empty result"}
            self._send_json(result)
        except Exception as e:
            logger.error(f"Chain validation error: {e}", exc_info=True)
            self._send_json({"error": str(e)}, status=500)
    def _handle_chain_execute(self):
        """POST /v1/chain/execute - Ejecutar cadena con rollback y recovery."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"error": f"Invalid JSON: {e}"}, status=400)
            return
        description = data.get("description", "")
        if not description:
            self._send_json({"error": "Missing 'description' field"}, status=400)
            return
        chain_data = data.get("data", {})
        recovery = data.get("recovery", "skip")
        try:
            result = _run_async(self.orchestrator.execute_logic_chain(description, chain_data, recovery))
            if result is None:
                result = {"error": "Orchestrator returned empty result"}
            self._send_json(result)
        except Exception as e:
            logger.error(f"Chain execution error: {e}", exc_info=True)
            self._send_json({"error": str(e)}, status=500)
    def _handle_context_index_post(self):
        """POST /v1/system/context-index - Indexar código para Context Pointers."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"error": f"Invalid JSON: {e}"}, status=400)
            return
        code = data.get("code", "")
        file_path = data.get("file_path", "input.py")
        if not code:
            self._send_json({"error": "Missing 'code' field"}, status=400)
            return
        try:
            cpe = getattr(self.orchestrator, '_context_pointer_engine', None)
            if cpe:
                count = cpe.index_code(code, file_path)
                compact_ctx, pointers = cpe.build_compact_context(data.get("query", ""), max_tokens=2000)
                self._send_json({
                    "indexed_signatures": count,
                    "compact_context": compact_ctx,
                    "pointers_count": len(pointers),
                    "stats": cpe.stats,
                })
            else:
                self._send_json({"error": "ContextPointerEngine not available"}, status=503)
        except Exception as e:
            logger.error(f"Context index error: {e}", exc_info=True)
            self._send_json({"error": str(e)}, status=500)
    def _handle_auto_evolve_trigger(self):
        """POST /v1/system/auto-evolve/trigger - Forzar ciclo de auto-evolución."""
        try:
            cron = getattr(self.orchestrator, '_niche_cron', None)
            if cron:
                result = cron.trigger_now()
                self._send_json(result)
            else:
                self._send_json({"error": "AutoEvolve cron not available"}, status=503)
        except Exception as e:
            logger.error(f"Auto-evolve trigger error: {e}", exc_info=True)
            self._send_json({"error": str(e)}, status=500)
    def _handle_dna_validate(self):
        """POST /v1/dna/validate - Validar código contra gates de calidad."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"error": f"Invalid JSON: {e}"}, status=400)
            return
        code = data.get("code", "")
        niche_name = data.get("niche", "")
        if not code:
            self._send_json({"error": "Missing 'code' field"}, status=400)
            return
        try:
            from src.core.template_engine import TemplateEngine
            engine = TemplateEngine()
            result = engine.validate_niche_code(code, niche_name)
            self._send_json(result)
        except Exception as e:
            logger.error(f"DNA validate error: {e}", exc_info=True)
            self._send_json({"error": str(e)}, status=500)
    def _handle_dna_polish(self):
        """POST /v1/dna/polish - Pulir texto técnico a corporativo."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"error": f"Invalid JSON: {e}"}, status=400)
            return
        text = data.get("text", "")
        if not text:
            self._send_json({"error": "Missing 'text' field"}, status=400)
            return
        try:
            from src.core.template_engine import TemplateEngine
            engine = TemplateEngine()
            polished = engine.polish_output(text)
            self._send_json({"original": text, "polished": polished})
        except Exception as e:
            logger.error(f"DNA polish error: {e}", exc_info=True)
            self._send_json({"error": str(e)}, status=500)

    def _handle_design_schema(self):
        """POST /v1/design/schema - Disenar esquema de BD."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"error": f"Invalid JSON: {e}"}, status=400)
            return
        description = data.get("description", "")
        if not description:
            self._send_json({"error": "Missing 'description' field"}, status=400)
            return
        try:
            result = _run_async(self.orchestrator.design_schema(description))
            if result is None:
                result = {"error": "Orchestrator returned empty result"}
            self._send_json(result)
        except Exception as e:
            logger.error(f"Schema design error: {e}", exc_info=True)
            self._send_json({"error": str(e)}, status=500)

