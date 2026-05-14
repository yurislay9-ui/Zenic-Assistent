"""
Phase 7 Auth & Logic Builder API mixin for BaseOrchestrator.
"""

from ._imports import logger


class Phase7Mixin:
    """Phase 7: Auth & Logic Builder API methods for BaseOrchestrator."""

    async def register_user(self, username: str, email: str, password: str,
                           role: str = "user") -> dict:
        """Registra un nuevo usuario en el sistema de autenticacion."""
        if not self._auth:
            return {"error": "AuthService not available"}
        return self._auth.register_user(username, email, password, role)

    async def login_user(self, username: str, password: str) -> dict:
        """Autentica un usuario y devuelve tokens JWT."""
        if not self._auth:
            return {"error": "AuthService not available"}
        return self._auth.login_user(username, password)

    async def verify_token(self, token: str) -> dict:
        """Verifica un token JWT."""
        if not self._auth:
            return {"error": "AuthService not available"}
        try:
            return self._auth.verify_token(token)
        except Exception as e:
            return {"error": str(e)}

    async def build_logic(self, description: str) -> dict:
        """Construye logica de negocio a partir de una descripcion."""
        if self._business_logic_agent:
            output = self._business_logic_agent.execute_with_runner(
                self._agent_runner,
                operation_type="custom",
                data={"description": description},
                description=description,
            )
            result = {
                "success": output.success,
                "data": output.data,
                "side_effects": output.side_effects,
                "insights": output.insights,
                "errors": output.errors,
                "source": output.source,
                "description": description,
            }
            if self._logic_builder:
                chain = self._logic_builder.build_from_description(description)
                blocks = [b.name for b in chain.blocks]
                # E-20 FIX: Replaced generate_process_method() (removed from LogicBuilder)
                # with generate_inline_block_code() from builder_registry.
                from src.core.logic_blocks.builder_registry import generate_inline_block_code, safe_var_name
                code_lines = []
                for i, block_name in enumerate(blocks):
                    var_name = safe_var_name(f"result_{block_name}_{i}")
                    code_lines.extend(generate_inline_block_code(block_name, var_name))
                code = "\n".join(code_lines)
                result["blocks"] = blocks
                result["block_count"] = len(blocks)
                result["generated_code"] = code
            return result

        if not self._logic_builder:
            return {"error": "LogicBuilder not available"}
        chain = self._logic_builder.build_from_description(description)
        blocks = [b.name for b in chain.blocks]
        # E-20 FIX: Replaced generate_process_method() (removed from LogicBuilder)
        # with generate_inline_block_code() from builder_registry.
        from src.core.logic_blocks.builder_registry import generate_inline_block_code, safe_var_name
        code_lines = []
        for i, block_name in enumerate(blocks):
            var_name = safe_var_name(f"result_{block_name}_{i}")
            code_lines.extend(generate_inline_block_code(block_name, var_name))
        code = "\n".join(code_lines)
        return {
            "blocks": blocks,
            "block_count": len(blocks),
            "generated_code": code,
            "description": description,
        }

    async def list_logic_blocks(self, category: str = "") -> list:
        """Lista bloques de logica disponibles."""
        if not self._logic_builder:
            return []
        blocks = self._logic_builder.list_blocks(category)
        return [
            {
                "name": b.name,
                "category": b.category,
                "description": b.description,
                "inputs": b.inputs,
                "outputs": b.outputs,
            }
            for b in blocks
        ]

    async def execute_action(self, action_type: str, config: dict) -> dict:
        """Ejecuta una accion individual usando el ActionExecutor."""
        if not self._executor_registry:
            return {"error": "ExecutorRegistry not available"}
        result = await self._executor_registry.execute_action(action_type, config, {})
        return {
            "success": result.success,
            "data": result.data,
            "error": result.error,
            "duration_ms": result.duration_ms,
        }
