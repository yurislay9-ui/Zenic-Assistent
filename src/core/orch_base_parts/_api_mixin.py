"""
Shared public API methods for BaseOrchestrator — app, automation, schema, think, list.
"""

from ._imports import logger


class APIMixin:
    """Shared public API methods for BaseOrchestrator."""

    @property
    def project_dir(self) -> str:
        """Project directory (preferred over deprecated p_dir)."""
        return self.p_dir

    async def resume_from_partial(self, resumption_token: str,
                                   subtask_index=None) -> dict:
        """Resume execution from a partial reasoning state."""
        return await self._partial_reasoning.resume_from_partial(
            resumption_token, subtask_index
        )

    async def generate_app(self, request: str, project_name: str = "",
                           output_dir: str = "") -> dict:
        """Genera una aplicacion completa a partir de una descripcion."""
        result = self._app_gen.generate_app(request, project_name, output_dir)

        if result.status == "generated" and self._memory is not None:
            self._memory.save_project(
                project_name=result.name,
                project_type=result.template_type,
                description=request,
                path=result.path,
                status="generated",
                entities=[e.get("name", "") for e in result.entities],
                endpoints=[str(ep) for ep in result.endpoints],
            )
            self._memory.save_episode(
                event_type="app_generated",
                description=f"Generated {result.template_type} app: {result.name}",
                context=request[:200],
                outcome="success" if result.status == "generated" else "failed",
                importance=0.8,
            )
            self._memory.learn_pattern(
                pattern_name=f"gen_{result.template_type}",
                pattern_type="app_generation",
                description=f"Generated {result.template_type} app from request",
                steps=[f"Used template: {result.template_type}",
                       f"Generated {len(result.files)} files"],
                success=result.status == "generated",
            )

        return {
            "status": result.status,
            "project_name": result.name,
            "template_type": result.template_type,
            "path": result.path,
            "files": result.files,
            "endpoints": result.endpoints,
            "entities": result.entities,
            "generation_time_s": result.generation_time_s,
            "error": result.error,
        }

    async def generate_automation(self, description: str,
                                   output_dir: str = "") -> dict:
        """Genera un proyecto de automatizacion a partir de una descripcion."""
        automation_design = None
        if self._automation_agent:
            from src.core.agents.schemas import AutomationInput
            automation_design = self._automation_agent.design_with_runner(
                self._agent_runner, description,
            )

        result = self._automation.generate_automation_project(description, output_dir)

        if automation_design:
            wf_dict = self._automation_agent.to_workflow_dict(automation_design)
            result["automation_agent"] = {
                "name": automation_design.name,
                "triggers": [
                    {"type": t.type, "config": t.config, "description": t.description}
                    for t in automation_design.triggers
                ],
                "actions": [
                    {"type": a.type, "config": a.config, "description": a.description}
                    for a in automation_design.actions
                ],
                "schedule": {
                    "type": automation_design.schedule.type,
                    "cron": automation_design.schedule.cron_expression,
                },
                "source": automation_design.source,
            }

        if self._memory is not None:
            wf = result.get("workflow")
            if wf:
                self._memory.save_episode(
                    event_type="automation_created",
                    description=f"Created automation: {wf.name}",
                    outcome="success",
                    importance=0.7,
                )

        workflow = result.get("workflow")
        workflow_info = None
        if workflow is not None:
            if isinstance(workflow, dict):
                workflow_info = {
                    "id": workflow.get("id", ""),
                    "name": workflow.get("name", ""),
                }
            else:
                workflow_info = {
                    "id": getattr(workflow, "id", ""),
                    "name": getattr(workflow, "name", ""),
                }

        return {
            "status": result.get("status", "unknown"),
            "path": result.get("path", ""),
            "files": result.get("files", []),
            "workflow": workflow_info,
            "automation_agent": result.get("automation_agent"),
        }

    async def design_schema(self, description: str) -> dict:
        """Disena un esquema de base de datos a partir de una descripcion."""
        schema = self._schema_designer.design_schema(description)
        sql = self._schema_designer.generate_sql(schema)
        models = self._schema_designer.generate_models(schema)
        init_sql = self._schema_designer.generate_init_sql(schema)

        return {
            "status": "designed",
            "tables": [{"name": t.name, "columns": len(t.columns)} for t in schema.tables],
            "sql": sql,
            "models": models,
            "init_sql": init_sql,
        }

    async def list_projects(self, status: str = "") -> list:
        """Lista proyectos generados."""
        if self._memory is not None:
            return self._memory.list_projects(status)
        return []

    async def list_automations(self) -> list:
        """Lista automatizaciones."""
        return self._automation.list_workflows()

    async def think(self, query: str, context: str = "") -> dict:
        """Usa ThinkingEngine para razonar sobre una pregunta."""
        result = self._thinking.reason(query, context)
        return {
            "answer": result.answer,
            "confidence": result.confidence,
            "source": result.source,
            "context_used": result.context_used,
            "thinking_time_s": result.thinking_time_s,
        }
