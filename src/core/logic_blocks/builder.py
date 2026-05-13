"""
ZENIC-AGENTS - LogicBuilder

Builder that composes LogicChains from descriptions, compositions, or templates.
Replaces the _process() placeholder with real business logic.
"""

import logging
from typing import Any, Dict, List, Optional

from .chain import LogicBlock, LogicChain
from .flow import (
    ConditionalBlock, LoopBlock, ParallelBlock, SwitchBlock, TryCatchBlock,
)
from .validation import (
    ValidateRequiredBlock, ValidateTypesBlock, ValidateRangesBlock,
    ValidateUniqueBlock, SanitizeBlock,
)
from .business_logic import (
    InvoiceCalculatorBlock, InventoryTrackerBlock, CRMPipelineBlock,
    TaskSchedulerBlock,
)
from .business_analytics import (
    ReportGeneratorBlock, NotificationDispatchBlock,
    DataAnalyzerBlock,
)
from .data import (
    CRUDCreateBlock, CRUDReadBlock, CRUDUpdateBlock, CRUDDeleteBlock,
)
from .data_transform import DataTransformBlock
from .integration import (
    EmailSendBlock, HTTPRequestBlock, WebhookCallBlock, FileOperationBlock,
)
from .auth import (
    AuthLoginBlock, AuthRegisterBlock, AuthVerifyBlock, AuthRBACBlock,
)
from .builder_registry import (
    build_keyword_map,
    map_template_block,
    get_block_template_code,
    generate_inline_block_code,
    safe_var_name,
)

logger = logging.getLogger(__name__)


# ============================================================
#  LOGIC BUILDER
# ============================================================


class LogicBuilder:
    """Construye LogicChains desde descripciones, composiciones, o templates.

    Motor principal que compone bloques de logica de negocio en cadenas
    ejecutables, reemplazando el _process() placeholder.
    """

    def __init__(self, template_engine: Optional[Any] = None) -> None:
        """Inicializa el LogicBuilder con bloques pre-construidos.

        Args:
            template_engine: Instancia de TemplateEngine para resolucion de templates
        """
        self._template_engine = template_engine
        self._blocks: Dict[str, LogicBlock] = {}
        self._chains: Dict[str, LogicChain] = {}
        self._keyword_map: Dict[str, List[str]] = {}

        # Register all built-in blocks
        self._register_builtin_blocks()
        self._keyword_map = build_keyword_map()

        logger.info(f"LogicBuilder: Initialized with {len(self._blocks)} blocks in {len(set(b.category for b in self._blocks.values()))} categories")

    # ============================================================
    #  BUILD METHODS
    # ============================================================

    def build_from_description(self, description: str) -> LogicChain:
        """Construye una LogicChain desde una descripcion en lenguaje natural.

        Usa keyword matching para identificar bloques relevantes y los
        compone en orden logico (validacion -> negocio -> datos -> salida).

        Args:
            description: Descripcion de la logica deseada

        Returns:
            LogicChain compuesta con los bloques relevantes
        """
        desc_lower = description.lower()
        suggested_blocks = set()

        # Match keywords to block names
        for keyword, block_names in self._keyword_map.items():
            if keyword in desc_lower:
                for bn in block_names:
                    suggested_blocks.add(bn)

        # Also use template_engine's suggest_blocks if available
        if self._template_engine and hasattr(self._template_engine, 'suggest_blocks'):
            try:
                template_suggestions = self._template_engine.suggest_blocks(description)
                for ts in template_suggestions:
                    # Map template block names to logic block names
                    mapped = map_template_block(ts)
                    if mapped:
                        suggested_blocks.add(mapped)
            except Exception as mapping_err:
                logger.debug(f"Block suggestion from template failed: {mapping_err}")

        # Organize blocks by category order (validation -> flow -> business_logic -> data -> integrations -> auth)
        category_order = ["validation", "flow", "business_logic", "data", "integrations", "auth"]
        ordered_blocks = []
        for cat in category_order:
            for bn in suggested_blocks:
                block = self._blocks.get(bn)
                if block and block.category == cat:
                    ordered_blocks.append(bn)

        # Add any remaining blocks not in category_order
        for bn in suggested_blocks:
            if bn not in ordered_blocks:
                ordered_blocks.append(bn)

        # Build chain
        chain = LogicChain(name=f"chain_{description[:30].replace(' ', '_')}")
        for block_name in ordered_blocks:
            block = self._blocks.get(block_name)
            if block:
                chain.add_block(block)

        logger.info(f"LogicBuilder: Built chain from description with {len(chain.blocks)} blocks: {chain.block_names}")
        return chain

    def build_from_blocks(self, block_names: List[str]) -> LogicChain:
        """Construye una LogicChain desde una lista de nombres de bloques.

        Args:
            block_names: Lista de nombres de bloques a componer

        Returns:
            LogicChain compuesta con los bloques especificados
        """
        chain = LogicChain(name=f"chain_{'_'.join(block_names[:3])}")
        for block_name in block_names:
            block = self._blocks.get(block_name)
            if block:
                chain.add_block(block)
            else:
                logger.warning(f"LogicBuilder: Block '{block_name}' not found, skipping")

        logger.info(f"LogicBuilder: Built chain from blocks: {chain.block_names}")
        return chain

    def build_for_template(self, template_type: str, entities: List[Dict]) -> LogicChain:
        """Construye una LogicChain optimizada para un tipo de template.

        Args:
            template_type: Tipo de template (e.g. 'crud', 'api', 'auth', 'report')
            entities: Lista de entidades del modelo

        Returns:
            LogicChain optimizada para el tipo de template
        """
        chain = LogicChain(name=f"chain_{template_type}")

        # Template-specific logic compositions
        template_compositions = {
            "crud": ["validate_required", "sanitize", "crud_create", "crud_read", "crud_update", "crud_delete"],
            "api": ["validate_required", "validate_types", "sanitize", "crud_create", "crud_read", "http_request"],
            "auth": ["validate_required", "sanitize", "auth_register", "auth_login", "auth_verify", "auth_rbac"],
            "report": ["validate_required", "data_analyzer", "report_generator", "file_operation"],
            "invoice": ["validate_required", "validate_types", "invoice_calculator", "crud_create", "email_send"],
            "inventory": ["validate_required", "inventory_tracker", "crud_update", "notification_dispatch"],
            "crm": ["validate_required", "sanitize", "crm_pipeline", "crud_update", "notification_dispatch"],
            "workflow": ["validate_required", "task_scheduler", "conditional", "notification_dispatch"],
            "notification": ["validate_required", "notification_dispatch", "email_send", "webhook_call"],
            "data_import": ["validate_required", "validate_types", "sanitize", "data_transform", "crud_create"],
            "data_export": ["validate_required", "crud_read", "data_transform", "file_operation", "email_send"],
        }

        block_names = template_compositions.get(template_type, ["validate_required", "sanitize"])

        for block_name in block_names:
            block = self._blocks.get(block_name)
            if block:
                chain.add_block(block)

        # Add entity-specific fields to chain data
        if entities:
            chain._entity_data = entities

        logger.info(f"LogicBuilder: Built chain for template '{template_type}' with {len(chain.blocks)} blocks")
        return chain

    # ============================================================
    #  BLOCK REGISTRY
    # ============================================================

    def register_block(self, block: LogicBlock):
        """Registra un bloque de logica personalizado."""
        self._blocks[block.name] = block
        # Update keyword map
        keywords = block.name.replace("_", " ").split()
        keywords.append(block.category)
        for kw in keywords:
            self._keyword_map.setdefault(kw, [])
            if block.name not in self._keyword_map[kw]:
                self._keyword_map[kw].append(block.name)
        logger.debug(f"LogicBuilder: Registered block '{block.name}' ({block.category})")

    def list_blocks(self, category: str = "") -> List[LogicBlock]:
        """Lista bloques disponibles, opcionalmente filtrados por categoria."""
        if category:
            return [b for b in self._blocks.values() if b.category == category]
        return list(self._blocks.values())

    def get_block(self, name: str) -> Optional[LogicBlock]:
        """Obtiene un bloque por nombre."""
        return self._blocks.get(name)

    # ============================================================
    #  CODE GENERATION
    # ============================================================

    def generate_process_method(self, block_names: List[str]) -> str:
        """Genera codigo fuente del metodo _process() desde bloques compuestos.

        Este metodo es critico: reemplaza el placeholder
        `return {"processed": True, "input": payload}` con logica real.

        Args:
            block_names: Lista de nombres de bloques a componer en el metodo

        Returns:
            String con codigo Python del metodo _process()
        """
        lines = [
            '    def _process(self, payload: Dict[str, Any]) -> Dict[str, Any]:',
            '        """Auto-generated by LogicBuilder - Real business logic."""',
            '        result = {}',
            '        context = {"db": self._db, "config": self.config}',
            '',
        ]

        step = 0
        for block_name in block_names:
            block = self._blocks.get(block_name)
            if not block:
                continue

            step += 1
            step_var = safe_var_name(block_name)

            # Try to get template from template_engine
            template_code = get_block_template_code(self._template_engine, block_name)

            if template_code:
                # Use template code
                lines.append(f'        # Step {step}: {block.description}')
                lines.append(f'        {step_var} = {template_code}')
            else:
                # Generate inline code based on block type
                inline_code = generate_inline_block_code(block_name, step_var)
                lines.append(f'        # Step {step}: {block.description}')
                for line in inline_code:
                    lines.append(f'        {line}')

            # Add error handling for each step
            if block.category == "validation":
                lines.append(f'        if not {step_var}.get("valid", True):')
                lines.append(f'            return {{"error": {step_var}.get("errors", "Validation failed"), "success": False}}')
                lines.append('')
            elif block_name == "validate_unique":
                lines.append(f'        if not {step_var}.get("is_unique", True):')
                lines.append(f'            return {{"error": "Value already exists", "success": False}}')
                lines.append('')
            elif block.category == "auth":
                lines.append(f'        if not {step_var}.get("success", True):')
                lines.append(f'            return {{"error": {step_var}.get("error", "Auth failed"), "success": False}}')
                lines.append('')
            else:
                lines.append(f'        result.update({step_var})')
                lines.append('')

        lines.append('        result["success"] = True')
        lines.append('        return result')

        return "\n".join(lines)

    # ============================================================
    #  INTERNAL HELPERS
    # ============================================================

    def _register_builtin_blocks(self):
        """Registra todos los bloques pre-construidos."""
        builtin_blocks = [
            # Flow
            ConditionalBlock(),
            LoopBlock(),
            ParallelBlock(),
            SwitchBlock(),
            TryCatchBlock(),
            # Validation
            ValidateRequiredBlock(),
            ValidateTypesBlock(),
            ValidateRangesBlock(),
            ValidateUniqueBlock(),
            SanitizeBlock(),
            # Business Logic
            InvoiceCalculatorBlock(),
            InventoryTrackerBlock(),
            CRMPipelineBlock(),
            TaskSchedulerBlock(),
            ReportGeneratorBlock(),
            NotificationDispatchBlock(),
            DataAnalyzerBlock(),
            # Data
            CRUDCreateBlock(),
            CRUDReadBlock(),
            CRUDUpdateBlock(),
            CRUDDeleteBlock(),
            DataTransformBlock(),
            # Integration
            EmailSendBlock(),
            HTTPRequestBlock(),
            WebhookCallBlock(),
            FileOperationBlock(),
            # Auth
            AuthLoginBlock(),
            AuthRegisterBlock(),
            AuthVerifyBlock(),
            AuthRBACBlock(),
        ]

        for block in builtin_blocks:
            self._blocks[block.name] = block

    # ============================================================
    #  STATS
    # ============================================================

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadisticas del LogicBuilder."""
        categories = {}
        for block in self._blocks.values():
            categories[block.category] = categories.get(block.category, 0) + 1

        return {
            "total_blocks": len(self._blocks),
            "categories": categories,
            "template_engine_connected": self._template_engine is not None,
            "keyword_map_size": len(self._keyword_map),
        }
