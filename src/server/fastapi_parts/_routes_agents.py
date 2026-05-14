"""
Agent / generation endpoints — /v1/generate/*, /v1/design/*,
/v1/think, /v1/reason, /v1/chain/*.

AI-powered endpoints that invoke the orchestrator for code generation,
thinking, reasoning, and logic-chain operations. Project runner endpoints
(/v1/project/*) are in _routes_admin.py.
"""

from typing import Any, Optional

from src.server.fastapi_parts._imports import (
    logging,
    logger,
    FeatureNotAvailableError,
    require_feature,
)


def register_agent_routes(
    app: Any,
    *,
    orchestrator: Any,
) -> None:
    """Register AI generation / agent routes on *app*."""

    from fastapi import Request, HTTPException

    # ── /v1/generate/app ────────────────────────────────────
    @app.post("/v1/generate/app")
    async def generate_app(request: Request):
        """Generate a complete application from description."""
        try:
            require_feature("app_generation")
        except FeatureNotAvailableError as e:
            raise HTTPException(status_code=403, detail=str(e))
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        description = body.get("description", "")
        if not description:
            raise HTTPException(status_code=400, detail="Missing 'description' field")
        try:
            result = await orchestrator.generate_app(
                description, body.get("project_name", ""), body.get("output_dir", "")
            )
            return result
        except Exception as e:
            logger.error("App generation error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # ── /v1/generate/automation ─────────────────────────────
    @app.post("/v1/generate/automation")
    async def generate_automation(request: Request):
        """Generate an automation from description."""
        try:
            require_feature("automation_generation")
        except FeatureNotAvailableError as e:
            raise HTTPException(status_code=403, detail=str(e))
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        description = body.get("description", "")
        if not description:
            raise HTTPException(status_code=400, detail="Missing 'description' field")
        try:
            result = await orchestrator.generate_automation(
                description, body.get("output_dir", "")
            )
            return result
        except Exception as e:
            logger.error("Automation generation error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # ── /v1/generate/niche ──────────────────────────────────
    @app.post("/v1/generate/niche")
    async def generate_niche(request: Request):
        """Generate an app from a predefined niche template."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        niche_name = body.get("niche", "")
        if not niche_name:
            raise HTTPException(status_code=400, detail="Missing 'niche' field")
        try:
            # TemplateEngine removed — module deleted
            raise HTTPException(status_code=501, detail="TemplateEngine removed — niche generation unavailable")
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Niche generation error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # ── /v1/generate/code ───────────────────────────────────
    @app.post("/v1/generate/code")
    async def generate_code(request: Request):
        """Generate real functional code from description using CodeAssembler."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        description = body.get("description", "")
        if not description:
            raise HTTPException(status_code=400, detail="Missing 'description' field")

        project_name = body.get("project_name", "zenic_app")
        entities = body.get("entities", [])
        language = body.get("language", "python")
        strategy = body.get("strategy", "auto")

        try:
            code_gen = getattr(orchestrator, "_code_gen", None)
            if not code_gen:
                raise HTTPException(status_code=503, detail="CodeGenerator not available")

            if strategy == "smart_chain" or (strategy == "auto" and not entities):
                result = code_gen.generate_fragmented(
                    task_description=description, language=language,
                    entity_info=entities[0] if entities else None,
                )
                return {
                    "status": "generated", "strategy": "smart_chain",
                    "code": result["code"], "success": result["success"],
                    "steps_completed": result["steps_completed"],
                    "steps_total": result["steps_total"],
                    "repair_count": result["repair_count"], "language": language,
                }

            result = code_gen.generate_real_code(
                description=description, niche_plan=None,
                entities=entities, project_name=project_name,
            )
            return {
                "status": "generated", "strategy": "assembler",
                "project_name": result.get("project_name", project_name),
                "total_files": result.get("total_files", 0),
                "files": {k: v[:200] + "..." if len(v) > 200 else v
                          for k, v in result.get("files", {}).items()},
                "validation": result.get("validation", {}),
                "blocks": result.get("blocks", []), "language": language,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Code generation error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # ── /v1/generate/tests ──────────────────────────────────
    @app.post("/v1/generate/tests")
    async def generate_tests(request: Request):
        """Auto-generate pytest tests for code (M9)."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        code = body.get("code", "")
        if not code:
            raise HTTPException(status_code=400, detail="Missing 'code' field")
        try:
            # TestGenerator removed — module deleted
            raise HTTPException(status_code=501, detail="TestGenerator removed — test generation unavailable")
        except HTTPException:
            raise

    # ── /v1/generate/multilang ──────────────────────────────
    @app.post("/v1/generate/multilang")
    async def generate_multilang(request: Request):
        """Generate API project in TypeScript, Go, or Kotlin (M10)."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        entities = body.get("entities", [])
        project_name = body.get("project_name", "")
        language = body.get("language", "")
        if not entities:
            raise HTTPException(status_code=400, detail="Missing 'entities' field")
        if not project_name:
            raise HTTPException(status_code=400, detail="Missing 'project_name' field")
        if language not in ("typescript", "go", "kotlin"):
            raise HTTPException(status_code=400, detail="Language must be 'typescript', 'go', or 'kotlin'")
        try:
            from src.core.multi_language import MultiLanguage
            gen = MultiLanguage()
            files = gen.generate_project(
                entities=entities, project_name=project_name,
                language=language, description=body.get("description", ""),
            )
            truncated = {k: v[:300] + "..." if len(v) > 300 else v for k, v in files.items()}
            return {
                "status": "generated", "language": language,
                "project_name": project_name, "total_files": len(files), "files": truncated,
            }
        except Exception as e:
            logger.error("Multilang generation error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # ── /v1/design/schema ───────────────────────────────────
    @app.post("/v1/design/schema")
    async def design_schema(request: Request):
        """Design a database schema from description."""
        try:
            require_feature("schema_design")
        except FeatureNotAvailableError as e:
            raise HTTPException(status_code=403, detail=str(e))
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        description = body.get("description", "")
        if not description:
            raise HTTPException(status_code=400, detail="Missing 'description' field")
        try:
            return await orchestrator.design_schema(description)
        except Exception as e:
            logger.error("Schema design error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # ── /v1/think ───────────────────────────────────────────
    @app.post("/v1/think")
    async def think(request: Request):
        """Thinking engine endpoint."""
        try:
            require_feature("thinking_engine")
        except FeatureNotAvailableError as e:
            raise HTTPException(status_code=403, detail=str(e))
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        query = body.get("query", "")
        if not query:
            raise HTTPException(status_code=400, detail="Missing 'query' field")
        try:
            return await orchestrator.think(query, body.get("context", ""))
        except Exception as e:
            logger.error("Thinking error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # ── /v1/reason ──────────────────────────────────────────
    @app.post("/v1/reason")
    async def reason(request: Request):
        """Advanced reasoning endpoint (Phase 8)."""
        try:
            require_feature("reasoning_engine")
        except FeatureNotAvailableError as e:
            raise HTTPException(status_code=403, detail=str(e))
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        query = body.get("query", "")
        if not query:
            raise HTTPException(status_code=400, detail="Missing 'query' field")
        try:
            return await orchestrator.reason(query, body.get("mode", "auto"), body.get("context", ""))
        except Exception as e:
            logger.error("Reasoning error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # ── /v1/chain/validate ──────────────────────────────────
    @app.post("/v1/chain/validate")
    async def chain_validate(request: Request):
        """Validate a logic chain."""
        try:
            require_feature("logic_chains")
        except FeatureNotAvailableError as e:
            raise HTTPException(status_code=403, detail=str(e))
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        description = body.get("description", "")
        if not description:
            raise HTTPException(status_code=400, detail="Missing 'description' field")
        try:
            return await orchestrator.validate_logic_chain(description)
        except Exception as e:
            logger.error("Chain validation error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # ── /v1/chain/execute ───────────────────────────────────
    @app.post("/v1/chain/execute")
    async def chain_execute(request: Request):
        """Execute a logic chain with rollback and recovery."""
        try:
            require_feature("logic_chains")
        except FeatureNotAvailableError as e:
            raise HTTPException(status_code=403, detail=str(e))
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        description = body.get("description", "")
        if not description:
            raise HTTPException(status_code=400, detail="Missing 'description' field")
        try:
            return await orchestrator.execute_logic_chain(
                description, body.get("data", {}), body.get("recovery", "skip")
            )
        except Exception as e:
            logger.error("Chain execution error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))
