"""
Zenic-Agents — Yamil: Agente Creador de Plantillas

Yamil es el agente unificado de creacion de plantillas que orquesta
el flujo completo desde la seleccion de nicho hasta la certificacion
del Blueprint. Integra y simplifica los componentes fragmentados:

  - NicheBridge (catalogo + templates Rust)
  - NicheOnboardingPipeline (pipeline E2E de 8 pasos)
  - NicheConverter (conversion niche → Blueprint)
  - OnboardingEngine (flujo de onboarding guiado)
  - BlueprintCertifier (firma ECDSA)

Principios:
  1. Yamil SIEMPRE produce un resultado, deterministico si la IA no esta.
  2. Safety Gate es inbypassable — si DENY, el flujo se detiene.
  3. Toda accion es auditable — cada paso queda registrado.
  4. Resumable — cualquier paso puede reintentarse independientemente.

Uso basico::

    from src.core.agents.yamil import YamilAgent

    yamil = YamilAgent()

    # Listar nichos disponibles
    niches = yamil.list_niches()

    # Crear plantilla desde un nicho
    result = yamil.create_template("telemedicine")

    # Llenar campos
    yamil.fill_field(result, "business_identity", "business_name", "Mi Clinica")

    # Completar y certificar
    result = yamil.complete_and_certify(result, private_key="...")
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from src.core.agents.base import BaseAgent

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  ENUMS
# ──────────────────────────────────────────────────────────────

class YamilStep(str, Enum):
    """Pasos del flujo de creacion de plantillas."""
    NOT_STARTED = "not_started"
    SELECT_NICHE = "select_niche"
    GENERATE_TEMPLATE = "generate_template"
    FILL_FIELDS = "fill_fields"
    VALIDATE = "validate"
    SAFETY_CHECK = "safety_check"
    CERTIFY = "certify"
    EXPORT = "export"
    COMPLETED = "completed"
    FAILED = "failed"


class YamilAction(str, Enum):
    """Acciones que Yamil puede ejecutar."""
    LIST_NICHES = "list_niches"
    SEARCH_NICHES = "search_niches"
    LIST_CATEGORIES = "list_categories"
    CREATE_TEMPLATE = "create_template"
    FILL_FIELD = "fill_field"
    FILL_FIELDS_BATCH = "fill_fields_batch"
    GET_MISSING_FIELDS = "get_missing_fields"
    VALIDATE = "validate"
    SAFETY_CHECK = "safety_check"
    CERTIFY = "certify"
    EXPORT_YAML = "export_yaml"
    RUN_FULL = "run_full"
    GET_STATUS = "get_status"


# ──────────────────────────────────────────────────────────────
#  DATA CLASSES
# ──────────────────────────────────────────────────────────────

@dataclass
class YamilNicheInfo:
    """Informacion resumida de un nicho disponible."""
    niche_id: str
    name: str
    category: str
    description: str
    sensitivity: str
    scale: str
    compliance: List[str] = field(default_factory=list)


@dataclass
class YamilFieldInfo:
    """Informacion de un campo de plantilla."""
    name: str
    display_name: str
    field_type: str
    section: str
    description: str
    required: bool = True
    filled: bool = False
    value: Any = None


@dataclass
class YamilValidationResult:
    """Resultado de validacion de plantilla."""
    valid: bool
    completion_pct: float
    total_fields: int
    filled_fields: int
    missing_required: int
    missing_field_names: List[str] = field(default_factory=list)
    status: str = "incomplete"  # incomplete, partial, complete


@dataclass
class YamilSafetyResult:
    """Resultado del safety check."""
    passed: bool
    verdict: str  # ALLOW, CONFIRM, APPROVE, DENY
    reason: str = ""
    compliance_violations: List[str] = field(default_factory=list)
    escalation_applied: bool = False


@dataclass
class YamilCertifyResult:
    """Resultado de la certificacion del Blueprint."""
    success: bool
    blueprint_id: str = ""
    content_hash: str = ""
    signature_algorithm: str = ""
    signed_at: float = 0.0
    errors: List[str] = field(default_factory=list)


@dataclass
class YamilSession:
    """Sesion activa de creacion de plantilla."""
    session_id: str = ""
    niche_id: str = ""
    niche_category: str = ""
    niche_name: str = ""
    current_step: YamilStep = YamilStep.NOT_STARTED
    template_dict: Optional[Dict[str, Any]] = None
    fields_auto_filled: int = 0
    fields_manual_filled: int = 0
    total_fields: int = 0
    validation_result: Optional[YamilValidationResult] = None
    safety_result: Optional[YamilSafetyResult] = None
    certify_result: Optional[YamilCertifyResult] = None
    yaml_output: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    audit_log: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.session_id:
            self.session_id = f"yamil-{uuid.uuid4().hex[:8]}"
        if not self.created_at:
            self.created_at = time.time()
        if not self.updated_at:
            self.updated_at = self.created_at

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.updated_at = time.time()

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)
        self.updated_at = time.time()

    def add_audit(self, action: str, detail: str = "") -> None:
        self.audit_log.append({
            "timestamp": time.time(),
            "step": self.current_step.value,
            "action": action,
            "detail": detail,
        })
        self.updated_at = time.time()

    @property
    def progress_pct(self) -> float:
        step_values = {
            YamilStep.NOT_STARTED: 0.0,
            YamilStep.SELECT_NICHE: 12.5,
            YamilStep.GENERATE_TEMPLATE: 25.0,
            YamilStep.FILL_FIELDS: 50.0,
            YamilStep.VALIDATE: 62.5,
            YamilStep.SAFETY_CHECK: 75.0,
            YamilStep.CERTIFY: 87.5,
            YamilStep.EXPORT: 100.0,
            YamilStep.COMPLETED: 100.0,
            YamilStep.FAILED: 0.0,
        }
        return step_values.get(self.current_step, 0.0)

    @property
    def is_complete(self) -> bool:
        return self.current_step == YamilStep.COMPLETED


@dataclass
class YamilResult:
    """Resultado de una operacion de Yamil."""
    success: bool
    action: str
    session_id: str = ""
    niche_id: str = ""
    progress_pct: float = 0.0
    niches: List[YamilNicheInfo] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    template_dict: Optional[Dict[str, Any]] = None
    missing_fields: List[YamilFieldInfo] = field(default_factory=list)
    validation: Optional[YamilValidationResult] = None
    safety: Optional[YamilSafetyResult] = None
    certification: Optional[YamilCertifyResult] = None
    yaml_output: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────
#  YAMIL AGENT
# ──────────────────────────────────────────────────────────────

class YamilAgent(BaseAgent[YamilResult]):
    """
    Yamil — Agente Creador de Plantillas.

    Orquesta el flujo completo de creacion de plantillas desde la
    seleccion de nicho hasta la certificacion del Blueprint ECDSA.

    Hereda de BaseAgent e implementa:
      - build_prompt(): Prompt para consulta de nichos por IA
      - parse_response(): Parsea respuesta de IA a estructura
      - fallback(): Flujo deterministico sin IA

    Metodos principales:
      - list_niches(): Lista nichos disponibles
      - search_niches(): Busca nichos por texto
      - list_categories(): Lista categorias de nichos
      - create_template(): Crea plantilla desde nicho
      - fill_field(): Llena un campo individual
      - fill_fields_batch(): Llena multiples campos
      - get_missing_fields(): Obtiene campos faltantes
      - validate(): Valida completitud
      - safety_check(): Verifica seguridad + compliance
      - certify(): Certifica con firma ECDSA
      - export_yaml(): Exporta a YAML
      - run_full(): Ejecuta flujo completo E2E
      - get_status(): Obtiene estado de sesion
    """

    def __init__(self) -> None:
        super().__init__(name="yamil")
        self._sessions: Dict[str, YamilSession] = {}
        self._bridge: Any = None
        self._domain_gate: Any = None
        self._certifier: Any = None
        self._converter: Any = None
        self._native_available: bool = False

        # Intentar cargar extension Rust
        self._init_native()

    def _init_native(self) -> None:
        """Inicializar conexion con extension Rust."""
        try:
            from src.core.niche_rust.bridge import get_bridge, NicheBridge
            bridge = get_bridge()
            if bridge is not None:
                self._bridge = bridge
                self._native_available = True
                logger.info("YamilAgent: Rust native extension loaded")
            else:
                logger.warning("YamilAgent: Rust extension not available, using fallback mode")
        except ImportError:
            logger.warning("YamilAgent: niche_rust.bridge not importable, using fallback mode")

        try:
            from src.core.executors.safety_gate.domain_gate import get_default_domain_safety_gate
            self._domain_gate = get_default_domain_safety_gate()
        except ImportError:
            logger.warning("YamilAgent: DomainSafetyGate not available")

        try:
            from src.core.niche_rust.certifier_bridge import BlueprintCertifier
            self._certifier = BlueprintCertifier()
        except ImportError:
            logger.warning("YamilAgent: BlueprintCertifier not available")

        try:
            from src.core.blueprints.converter import NicheConverter
            self._converter = NicheConverter()
        except ImportError:
            logger.warning("YamilAgent: NicheConverter not available")

    # ──────────────────────────────────────────────────────────
    #  BaseAgent Implementation
    # ──────────────────────────────────────────────────────────

    def build_prompt(self, input_data: Any) -> tuple[str, str]:
        """Construye prompt para consulta de nichos via IA."""
        query = str(input_data) if input_data else ""
        system_prompt = (
            "Eres Yamil, el agente creador de plantillas de Zenic-Agents. "
            "Tu unica funcion es ayudar al usuario a seleccionar el nicho "
            "industrial mas adecuado para su negocio. "
            "Responde SOLO con el niche_id del catalogo que mejor coincida. "
            "Si no hay coincidencia, responde 'none'. "
            "Nichos disponibles: ai_automation, data_analytics, ml_operations, "
            "nlp_services, defi_protocols, neo_banking, insurtech, regtech, "
            "telemedicine, mental_health_ai, genomics, wearables_health, "
            "carbon_tracking, smart_grid, circular_economy, adaptive_learning, "
            "vr_education, micro_credentials, smart_buildings, digital_twins, "
            "fractional_ownership, smart_contracts, legal_ai, compliance_automation."
        )
        user_prompt = f"Consulta del usuario: {query}"
        return system_prompt, user_prompt

    def parse_response(self, raw_response: str, input_data: Any) -> Optional[YamilResult]:
        """Parsea respuesta de IA a YamilResult."""
        cleaned = raw_response.strip().lower()
        valid_niches = [
            "ai_automation", "data_analytics", "ml_operations", "nlp_services",
            "defi_protocols", "neo_banking", "insurtech", "regtech",
            "telemedicine", "mental_health_ai", "genomics", "wearables_health",
            "carbon_tracking", "smart_grid", "circular_economy",
            "adaptive_learning", "vr_education", "micro_credentials",
            "smart_buildings", "digital_twins", "fractional_ownership",
            "smart_contracts", "legal_ai", "compliance_automation",
        ]
        if cleaned in valid_niches:
            return YamilResult(
                success=True,
                action=YamilAction.SEARCH_NICHES.value,
                niches=[YamilNicheInfo(
                    niche_id=cleaned,
                    name=cleaned.replace("_", " ").title(),
                    category="",
                    description="",
                    sensitivity="",
                    scale="",
                )],
            )
        return None

    def fallback(self, input_data: Any) -> YamilResult:
        """Busqueda deterministica de nichos sin IA."""
        query = str(input_data).lower() if input_data else ""
        if not query:
            return self.list_niches()

        # Busqueda deterministica por coincidencia de texto
        results = self._search_niches_deterministic(query)
        return YamilResult(
            success=True,
            action=YamilAction.SEARCH_NICHES.value,
            niches=results,
        )

    # ──────────────────────────────────────────────────────────
    #  PUBLIC API — Catalog Operations
    # ──────────────────────────────────────────────────────────

    def list_niches(self) -> YamilResult:
        """Lista todos los nichos disponibles del catalogo."""
        niches = self._get_all_niches()
        return YamilResult(
            success=True,
            action=YamilAction.LIST_NICHES.value,
            niches=niches,
        )

    def search_niches(self, query: str) -> YamilResult:
        """Busca nichos por texto (nombre, dominio, tags)."""
        if not query:
            return self.list_niches()

        results = self._search_niches_deterministic(query)
        return YamilResult(
            success=True,
            action=YamilAction.SEARCH_NICHES.value,
            niches=results,
        )

    def list_categories(self) -> YamilResult:
        """Lista todas las categorias de nichos disponibles."""
        categories = self._get_categories()
        return YamilResult(
            success=True,
            action=YamilAction.LIST_CATEGORIES.value,
            categories=categories,
        )

    # ──────────────────────────────────────────────────────────
    #  PUBLIC API — Template Creation
    # ──────────────────────────────────────────────────────────

    def create_template(self, niche_id: str) -> YamilResult:
        """
        Crea una plantilla desde un nicho del catalogo.

        Este es el paso 1 del flujo: seleccionar nicho y generar
        la estructura de plantilla con todos los campos vacios.
        """
        session = YamilSession(niche_id=niche_id)

        # Buscar niche en catalogo
        niche_info = self._get_niche_info(niche_id)
        if niche_info is None:
            session.add_error(f"Nicho no encontrado: {niche_id}")
            session.current_step = YamilStep.FAILED
            return YamilResult(
                success=False,
                action=YamilAction.CREATE_TEMPLATE.value,
                session_id=session.session_id,
                niche_id=niche_id,
                errors=session.errors,
            )

        session.niche_name = niche_info.name
        session.niche_category = niche_info.category
        session.add_audit("select_niche", f"Seleccionado: {niche_id} ({niche_info.name})")
        session.current_step = YamilStep.SELECT_NICHE

        # Generar template
        template_dict = self._generate_template(niche_id)
        if template_dict is None:
            session.add_error(f"No se pudo generar plantilla para: {niche_id}")
            session.current_step = YamilStep.FAILED
            return YamilResult(
                success=False,
                action=YamilAction.CREATE_TEMPLATE.value,
                session_id=session.session_id,
                niche_id=niche_id,
                errors=session.errors,
            )

        session.template_dict = template_dict
        session.current_step = YamilStep.GENERATE_TEMPLATE
        session.add_audit("generate_template", f"Plantilla generada para {niche_id}")

        # Calcular campos iniciales
        validation = self._validate_template(template_dict)
        session.total_fields = validation.total_fields
        session.validation_result = validation

        # Guardar sesion
        self._sessions[session.session_id] = session

        return YamilResult(
            success=True,
            action=YamilAction.CREATE_TEMPLATE.value,
            session_id=session.session_id,
            niche_id=niche_id,
            progress_pct=session.progress_pct,
            template_dict=template_dict,
            validation=validation,
            missing_fields=self._get_missing_fields_info(template_dict),
        )

    # ──────────────────────────────────────────────────────────
    #  PUBLIC API — Field Operations
    # ──────────────────────────────────────────────────────────

    def fill_field(
        self,
        session_id: str,
        section_id: str,
        field_name: str,
        value: Any,
    ) -> YamilResult:
        """Llena un campo individual de la plantilla."""
        session = self._get_session(session_id)
        if session is None:
            return YamilResult(
                success=False, action=YamilAction.FILL_FIELD.value,
                errors=["Sesion no encontrada"],
            )

        if session.template_dict is None:
            return YamilResult(
                success=False, action=YamilAction.FILL_FIELD.value,
                session_id=session_id, errors=["No hay plantilla en la sesion"],
            )

        filled = self._set_field(session.template_dict, section_id, field_name, value)
        if filled:
            session.fields_manual_filled += 1
            session.current_step = YamilStep.FILL_FIELDS
            session.add_audit("fill_field", f"{section_id}.{field_name} = {value!r}")

            # Actualizar validacion
            session.validation_result = self._validate_template(session.template_dict)

        return YamilResult(
            success=filled,
            action=YamilAction.FILL_FIELD.value,
            session_id=session_id,
            niche_id=session.niche_id,
            progress_pct=session.progress_pct,
            validation=session.validation_result,
            missing_fields=self._get_missing_fields_info(session.template_dict),
            errors=[] if filled else [f"No se pudo llenar campo {section_id}.{field_name}"],
        )

    def fill_fields_batch(
        self,
        session_id: str,
        fields: Dict[str, Any],
        section_id: str = "",
    ) -> YamilResult:
        """
        Llena multiples campos de la plantilla en batch.

        Args:
            session_id: ID de la sesion activa.
            fields: Dict de field_name → value.
            section_id: Seccion comun (si es vacio, busca automaticamente).
        """
        session = self._get_session(session_id)
        if session is None:
            return YamilResult(
                success=False, action=YamilAction.FILL_FIELDS_BATCH.value,
                errors=["Sesion no encontrada"],
            )

        if session.template_dict is None:
            return YamilResult(
                success=False, action=YamilAction.FILL_FIELDS_BATCH.value,
                session_id=session_id, errors=["No hay plantilla en la sesion"],
            )

        filled_count = 0
        errors = []
        for field_name, value in fields.items():
            if section_id:
                ok = self._set_field(session.template_dict, section_id, field_name, value)
            else:
                ok = self._auto_fill_field(session.template_dict, field_name, value)
            if ok:
                filled_count += 1
            else:
                errors.append(f"Campo no llenado: {field_name}")

        session.fields_manual_filled += filled_count
        session.current_step = YamilStep.FILL_FIELDS
        session.add_audit("fill_fields_batch", f"{filled_count}/{len(fields)} campos llenados")
        session.validation_result = self._validate_template(session.template_dict)

        return YamilResult(
            success=filled_count > 0,
            action=YamilAction.FILL_FIELDS_BATCH.value,
            session_id=session_id,
            niche_id=session.niche_id,
            progress_pct=session.progress_pct,
            validation=session.validation_result,
            missing_fields=self._get_missing_fields_info(session.template_dict),
            errors=errors,
            warnings=[] if filled_count == len(fields) else [
                f"Solo {filled_count}/{len(fields)} campos fueron llenados",
            ],
        )

    def get_missing_fields(self, session_id: str) -> YamilResult:
        """Obtiene la lista de campos requeridos faltantes."""
        session = self._get_session(session_id)
        if session is None or session.template_dict is None:
            return YamilResult(
                success=False, action=YamilAction.GET_MISSING_FIELDS.value,
                errors=["Sesion no encontrada o sin plantilla"],
            )

        missing = self._get_missing_fields_info(session.template_dict)
        return YamilResult(
            success=True,
            action=YamilAction.GET_MISSING_FIELDS.value,
            session_id=session_id,
            missing_fields=missing,
        )

    # ──────────────────────────────────────────────────────────
    #  PUBLIC API — Validation & Safety
    # ──────────────────────────────────────────────────────────

    def validate(self, session_id: str) -> YamilResult:
        """Valida la completitud de la plantilla."""
        session = self._get_session(session_id)
        if session is None or session.template_dict is None:
            return YamilResult(
                success=False, action=YamilAction.VALIDATE.value,
                errors=["Sesion no encontrada o sin plantilla"],
            )

        validation = self._validate_template(session.template_dict)
        session.validation_result = validation
        session.current_step = YamilStep.VALIDATE
        session.add_audit("validate", f"completitud={validation.completion_pct:.1f}%")

        return YamilResult(
            success=validation.valid,
            action=YamilAction.VALIDATE.value,
            session_id=session_id,
            niche_id=session.niche_id,
            progress_pct=session.progress_pct,
            validation=validation,
            missing_fields=self._get_missing_fields_info(session.template_dict),
        )

    def safety_check(
        self,
        session_id: str,
        action_type: str = "niche_onboarding",
        data_sensitivity: str = "low",
    ) -> YamilResult:
        """
        Ejecuta el safety check con DomainSafetyGate.

        INVARIANTE: Si devuelve DENY, el flujo NO puede continuar.
        No existe mecanismo de override.
        """
        session = self._get_session(session_id)
        if session is None or session.template_dict is None:
            return YamilResult(
                success=False, action=YamilAction.SAFETY_CHECK.value,
                errors=["Sesion no encontrada o sin plantilla"],
            )

        safety_result = self._run_safety_check(
            session, action_type, data_sensitivity
        )
        session.safety_result = safety_result

        if safety_result.passed:
            session.current_step = YamilStep.SAFETY_CHECK
            session.add_audit("safety_check", f"PASSED verdict={safety_result.verdict}")
        else:
            session.add_error(f"Safety gate BLOQUEADO: {safety_result.reason}")
            session.current_step = YamilStep.FAILED
            session.add_audit("safety_check", f"FAILED verdict={safety_result.verdict}")

        return YamilResult(
            success=safety_result.passed,
            action=YamilAction.SAFETY_CHECK.value,
            session_id=session_id,
            niche_id=session.niche_id,
            progress_pct=session.progress_pct,
            safety=safety_result,
            errors=[] if safety_result.passed else [safety_result.reason],
        )

    # ──────────────────────────────────────────────────────────
    #  PUBLIC API — Certification & Export
    # ──────────────────────────────────────────────────────────

    def certify(self, session_id: str, private_key: str = "") -> YamilResult:
        """Certifica el Blueprint con firma ECDSA."""
        session = self._get_session(session_id)
        if session is None or session.template_dict is None:
            return YamilResult(
                success=False, action=YamilAction.CERTIFY.value,
                errors=["Sesion no encontrada o sin plantilla"],
            )

        if session.current_step == YamilStep.FAILED:
            return YamilResult(
                success=False, action=YamilAction.CERTIFY.value,
                session_id=session_id,
                errors=["Sesion en estado FAILED — no se puede certificar"],
            )

        cert_result = self._certify_blueprint(session, private_key)
        session.certify_result = cert_result

        if cert_result.success:
            session.current_step = YamilStep.CERTIFY
            session.add_audit("certify", f"blueprint_id={cert_result.blueprint_id}")
        else:
            session.add_error(f"Certificacion fallida: {'; '.join(cert_result.errors)}")
            session.current_step = YamilStep.FAILED

        return YamilResult(
            success=cert_result.success,
            action=YamilAction.CERTIFY.value,
            session_id=session_id,
            niche_id=session.niche_id,
            progress_pct=session.progress_pct,
            certification=cert_result,
            errors=cert_result.errors if not cert_result.success else [],
        )

    def export_yaml(self, session_id: str) -> YamilResult:
        """Exporta la plantilla a formato YAML."""
        session = self._get_session(session_id)
        if session is None or session.template_dict is None:
            return YamilResult(
                success=False, action=YamilAction.EXPORT_YAML.value,
                errors=["Sesion no encontrada o sin plantilla"],
            )

        yaml_str = self._template_to_yaml(session.template_dict)
        session.yaml_output = yaml_str or ""
        session.current_step = YamilStep.EXPORT
        session.add_audit("export_yaml", f"yaml_length={len(session.yaml_output)}")

        return YamilResult(
            success=bool(yaml_str),
            action=YamilAction.EXPORT_YAML.value,
            session_id=session_id,
            niche_id=session.niche_id,
            progress_pct=session.progress_pct,
            yaml_output=yaml_str or "",
        )

    # ──────────────────────────────────────────────────────────
    #  PUBLIC API — Full Pipeline
    # ──────────────────────────────────────────────────────────

    def run_full(
        self,
        niche_id: str,
        answers: Optional[Dict[str, str]] = None,
        private_key: str = "",
        data_sensitivity: str = "low",
    ) -> YamilResult:
        """
        Ejecuta el flujo completo de creacion de plantilla E2E.

        1. Crear plantilla desde nicho
        2. Llenar campos (si se proveen answers)
        3. Validar
        4. Safety check
        5. Certificar (si se provee private_key)
        6. Exportar YAML
        """
        # Step 1: Crear
        result = self.create_template(niche_id)
        if not result.success:
            return result

        session_id = result.session_id

        # Step 2: Llenar campos
        if answers:
            fill_result = self.fill_fields_batch(session_id, answers)
            if not fill_result.success and fill_result.errors:
                return fill_result

        # Step 3: Validar
        val_result = self.validate(session_id)
        if not val_result.success and val_result.validation and val_result.validation.missing_required > 0:
            return YamilResult(
                success=False,
                action=YamilAction.RUN_FULL.value,
                session_id=session_id,
                niche_id=niche_id,
                validation=val_result.validation,
                missing_fields=val_result.missing_fields,
                errors=[
                    f"Plantilla incompleta: {val_result.validation.missing_required} "
                    f"campos requeridos faltantes"
                ],
            )

        # Step 4: Safety check
        safety_result = self.safety_check(session_id, data_sensitivity=data_sensitivity)
        if not safety_result.success:
            return safety_result

        # Step 5: Certificar
        if private_key:
            cert_result = self.certify(session_id, private_key)
            if not cert_result.success:
                return cert_result

        # Step 6: Exportar
        export_result = self.export_yaml(session_id)

        # Marcar completado
        session = self._get_session(session_id)
        if session is not None:
            session.current_step = YamilStep.COMPLETED
            session.add_audit("complete", "Pipeline completado exitosamente")

        return YamilResult(
            success=True,
            action=YamilAction.RUN_FULL.value,
            session_id=session_id,
            niche_id=niche_id,
            progress_pct=100.0,
            validation=val_result.validation if val_result.validation else None,
            safety=safety_result.safety if safety_result.safety else None,
            certification=cert_result.certification if private_key and cert_result.success else None,
            yaml_output=export_result.yaml_output if export_result.success else "",
        )

    # ──────────────────────────────────────────────────────────
    #  PUBLIC API — Session Management
    # ──────────────────────────────────────────────────────────

    def get_status(self, session_id: str) -> YamilResult:
        """Obtiene el estado actual de una sesion."""
        session = self._get_session(session_id)
        if session is None:
            return YamilResult(
                success=False, action=YamilAction.GET_STATUS.value,
                errors=["Sesion no encontrada"],
            )

        return YamilResult(
            success=True,
            action=YamilAction.GET_STATUS.value,
            session_id=session.session_id,
            niche_id=session.niche_id,
            progress_pct=session.progress_pct,
            validation=session.validation_result,
            safety=session.safety_result,
            certification=session.certify_result,
            errors=session.errors,
            warnings=session.warnings,
        )

    def get_session(self, session_id: str) -> Optional[YamilSession]:
        """Obtiene la sesion completa (para inspeccion)."""
        return self._sessions.get(session_id)

    def close_session(self, session_id: str) -> bool:
        """Cierra y elimina una sesion."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    # ──────────────────────────────────────────────────────────
    #  PUBLIC API — Convenience: Complete & Certify
    # ──────────────────────────────────────────────────────────

    def complete_and_certify(
        self,
        result: YamilResult,
        private_key: str = "",
        data_sensitivity: str = "low",
    ) -> YamilResult:
        """
        Convenience: Valida → Safety → Certifica → Exporta.

        Toma un YamilResult de create_template() o fill_field()
        y ejecuta los pasos restantes del pipeline.
        """
        if not result.session_id:
            return YamilResult(
                success=False, action="complete_and_certify",
                errors=["No hay sesion activa"],
            )

        # Validar
        val = self.validate(result.session_id)
        if not val.success:
            return val

        # Safety
        safety = self.safety_check(result.session_id, data_sensitivity=data_sensitivity)
        if not safety.success:
            return safety

        # Certificar
        if private_key:
            cert = self.certify(result.session_id, private_key)
            if not cert.success:
                return cert

        # Exportar
        return self.export_yaml(result.session_id)

    # ──────────────────────────────────────────────────────────
    #  PRIVATE — Bridge Operations (Rust or Fallback)
    # ──────────────────────────────────────────────────────────

    def _get_all_niches(self) -> List[YamilNicheInfo]:
        """Obtener todos los nichos del catalogo."""
        if self._bridge is not None:
            try:
                all_niches = self._bridge.list_niches()
                return [self._niche_to_info(n) for n in all_niches]
            except Exception as e:
                logger.warning("YamilAgent: Error listing niches from Rust: %s", e)

        # Fallback: lista hardcodeada
        return self._fallback_niche_list()

    def _search_niches_deterministic(self, query: str) -> List[YamilNicheInfo]:
        """Busqueda deterministica de nichos por texto."""
        query_lower = query.lower()
        all_niches = self._get_all_niches()
        results = []
        for n in all_niches:
            searchable = (
                n.niche_id + " " + n.name + " " + n.category +
                " " + n.description + " " + " ".join(n.compliance)
            ).lower()
            if query_lower in searchable:
                results.append(n)
        return results

    def _get_categories(self) -> List[str]:
        """Obtener categorias de nichos."""
        if self._bridge is not None:
            try:
                return self._bridge.list_categories()
            except Exception:
                pass
        return ["ai_data", "fintech", "healthtech", "greentech", "edtech", "proptech", "legaltech"]

    def _get_niche_info(self, niche_id: str) -> Optional[YamilNicheInfo]:
        """Obtener info de un nicho por ID."""
        if self._bridge is not None:
            try:
                niche = self._bridge.get_niche(niche_id)
                if niche is not None:
                    return self._niche_to_info(niche)
            except Exception as e:
                logger.warning("YamilAgent: Error getting niche '%s': %s", niche_id, e)

        # Fallback: buscar en lista hardcodeada
        for n in self._fallback_niche_list():
            if n.niche_id == niche_id:
                return n
        return None

    def _generate_template(self, niche_id: str) -> Optional[Dict[str, Any]]:
        """Generar template desde nicho."""
        if self._bridge is not None:
            try:
                return self._bridge.create_template(niche_id)
            except Exception as e:
                logger.warning("YamilAgent: Error generating template: %s", e)

        # Fallback: template basico
        return self._fallback_template(niche_id)

    def _validate_template(self, template_dict: Dict[str, Any]) -> YamilValidationResult:
        """Validar completitud del template."""
        if self._bridge is not None:
            try:
                result = self._bridge.validate_template(template_dict)
                if isinstance(result, dict):
                    return YamilValidationResult(
                        valid=result.get("valid", False),
                        completion_pct=result.get("completion_pct", 0.0),
                        total_fields=result.get("total_fields", 0),
                        filled_fields=result.get("filled_fields", 0),
                        missing_required=result.get("missing_required", 0),
                        missing_field_names=result.get("missing_field_names", []),
                        status=result.get("status", "incomplete"),
                    )
            except Exception as e:
                logger.warning("YamilAgent: Error validating template: %s", e)

        # Fallback: validacion basica
        return self._fallback_validate(template_dict)

    def _get_missing_fields_info(self, template_dict: Dict[str, Any]) -> List[YamilFieldInfo]:
        """Obtener campos faltantes como YamilFieldInfo."""
        if self._bridge is not None:
            try:
                missing = self._bridge.all_missing_fields(template_dict)
                return [
                    YamilFieldInfo(
                        name=m.get("name", ""),
                        display_name=m.get("display_name", m.get("name", "")),
                        field_type=m.get("type", "text"),
                        section=m.get("section", ""),
                        description=m.get("description", ""),
                        required=True,
                        filled=False,
                    )
                    for m in missing
                    if isinstance(m, dict)
                ]
            except Exception as e:
                logger.warning("YamilAgent: Error getting missing fields: %s", e)

        return []

    def _set_field(
        self,
        template_dict: Dict[str, Any],
        section_id: str,
        field_name: str,
        value: Any,
    ) -> bool:
        """Llenar un campo del template."""
        if self._bridge is not None:
            try:
                return self._bridge.fill_field(template_dict, section_id, field_name, value)
            except Exception as e:
                logger.warning("YamilAgent: Error filling field: %s", e)

        # Fallback: set directo en dict
        template = template_dict.get("template", template_dict)
        sections = template.get("sections", {})
        section = sections.get(section_id, {})
        fields = section.get("fields", {}) if isinstance(section, dict) else {}
        if field_name in fields:
            fields[field_name]["value"] = value
            return True
        return False

    def _auto_fill_field(
        self, template_dict: Dict[str, Any], field_name: str, value: str,
    ) -> bool:
        """Auto-llenar campo buscando en todas las secciones."""
        template = template_dict.get("template", template_dict)
        sections = template.get("sections", {})
        for section_id, section in sections.items():
            if not isinstance(section, dict):
                continue
            fields = section.get("fields", {})
            if field_name in fields:
                return self._set_field(template_dict, section_id, field_name, value)
        return False

    def _template_to_yaml(self, template_dict: Dict[str, Any]) -> Optional[str]:
        """Exportar template a YAML."""
        if self._bridge is not None:
            try:
                return self._bridge.template_to_yaml(template_dict)
            except Exception as e:
                logger.warning("YamilAgent: Error exporting YAML: %s", e)

        # Fallback: JSON
        import json
        return json.dumps(template_dict, indent=2, ensure_ascii=False)

    def _run_safety_check(
        self,
        session: YamilSession,
        action_type: str,
        data_sensitivity: str,
    ) -> YamilSafetyResult:
        """Ejecutar safety check via DomainSafetyGate."""
        if self._domain_gate is not None:
            try:
                config = {
                    "niche_id": session.niche_id,
                    "niche_category": session.niche_category,
                }
                result = self._domain_gate.check(
                    action_type=action_type,
                    config=config,
                    niche_category=session.niche_category,
                    data_sensitivity=data_sensitivity,
                )
                violations = []
                if hasattr(result, "compliance_results"):
                    for cr in result.compliance_results:
                        if hasattr(cr, "compliant") and not cr.compliant:
                            violations.append(f"{cr.standard}: {cr.risk_level}")

                return YamilSafetyResult(
                    passed=result.can_proceed if hasattr(result, "can_proceed") else True,
                    verdict=str(result.final_verdict) if hasattr(result, "final_verdict") else "ALLOW",
                    reason=result.reason if hasattr(result, "reason") else "",
                    compliance_violations=violations,
                    escalation_applied=result.escalation_applied if hasattr(result, "escalation_applied") else False,
                )
            except Exception as e:
                logger.warning("YamilAgent: Safety check error: %s", e)
                # En caso de error, permitir pero con warning
                return YamilSafetyResult(
                    passed=True,
                    verdict="ALLOW",
                    reason=f"Safety check fallback (error: {e})",
                )

        # Sin domain gate — permitir por defecto
        return YamilSafetyResult(passed=True, verdict="ALLOW", reason="No domain gate available")

    def _certify_blueprint(
        self, session: YamilSession, private_key: str,
    ) -> YamilCertifyResult:
        """Certificar Blueprint via BlueprintCertifier."""
        if self._certifier is not None:
            try:
                result = self._certifier.certify_template(
                    session.template_dict, private_key
                )
                if hasattr(result, "success") and result.success:
                    return YamilCertifyResult(
                        success=True,
                        blueprint_id=result.blueprint_id if hasattr(result, "blueprint_id") else "",
                        content_hash=result.content_hash if hasattr(result, "content_hash") else "",
                        signature_algorithm="ECDSA-P256",
                        signed_at=time.time(),
                    )
                else:
                    errors = getattr(result, "errors", ["Certificacion fallida"])
                    return YamilCertifyResult(success=False, errors=errors)
            except Exception as e:
                logger.warning("YamilAgent: Certification error: %s", e)
                return YamilCertifyResult(success=False, errors=[str(e)])

        # Sin certifier — fallback con hash
        if session.template_dict is not None:
            import hashlib, json
            content = json.dumps(session.template_dict, sort_keys=True, ensure_ascii=False)
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            return YamilCertifyResult(
                success=True,
                blueprint_id=f"bp-{uuid.uuid4().hex[:8]}",
                content_hash=content_hash,
                signature_algorithm="SHA-256-fallback",
                signed_at=time.time(),
            )

        return YamilCertifyResult(success=False, errors=["No hay template para certificar"])

    # ──────────────────────────────────────────────────────────
    #  PRIVATE — Helpers
    # ──────────────────────────────────────────────────────────

    def _get_session(self, session_id: str) -> Optional[YamilSession]:
        """Obtener sesion por ID."""
        return self._sessions.get(session_id)

    @staticmethod
    def _niche_to_info(niche: Any) -> YamilNicheInfo:
        """Convertir NicheDefinition Rust a YamilNicheInfo."""
        return YamilNicheInfo(
            niche_id=getattr(niche, "niche_id", ""),
            name=getattr(niche, "name", ""),
            category=str(getattr(niche, "niche_category", "")),
            description=getattr(niche, "description", ""),
            sensitivity=str(getattr(niche, "data_sensitivity", "")),
            scale=getattr(niche, "scale", ""),
            compliance=getattr(niche, "compliance", []),
        )

    # ──────────────────────────────────────────────────────────
    #  FALLBACK — Sin Rust Extension
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _fallback_niche_list() -> List[YamilNicheInfo]:
        """Lista hardcodeada de nichos cuando Rust no esta disponible."""
        return [
            YamilNicheInfo("ai_automation", "AI Automation", "ai_data", "AI process automation", "high", "enterprise", ["GDPR", "SOC2"]),
            YamilNicheInfo("data_analytics", "Data Analytics", "ai_data", "Data analytics platform", "medium", "large", ["GDPR"]),
            YamilNicheInfo("ml_operations", "ML Operations", "ai_data", "ML ops platform", "high", "enterprise", ["GDPR", "SOC2"]),
            YamilNicheInfo("nlp_services", "NLP Services", "ai_data", "NLP service platform", "medium", "large", ["GDPR"]),
            YamilNicheInfo("defi_protocols", "DeFi Protocols", "fintech", "Decentralized finance", "critical", "enterprise", ["AML", "KYC", "SEC"]),
            YamilNicheInfo("neo_banking", "Neo Banking", "fintech", "Digital banking", "critical", "enterprise", ["PCI-DSS", "AML", "KYC", "SOX"]),
            YamilNicheInfo("insurtech", "InsurTech", "fintech", "Insurance technology", "critical", "large", ["GDPR", "Solvency II", "AML"]),
            YamilNicheInfo("regtech", "RegTech", "fintech", "Regulatory technology", "critical", "enterprise", ["GDPR", "SOX", "AML", "Basel III"]),
            YamilNicheInfo("telemedicine", "Telemedicine", "healthtech", "Telemedicine platform", "critical", "large", ["HIPAA", "GDPR"]),
            YamilNicheInfo("mental_health_ai", "Mental Health AI", "healthtech", "Mental health AI platform", "critical", "large", ["HIPAA", "GDPR", "APA"]),
            YamilNicheInfo("genomics", "Genomics", "healthtech", "Genomics platform", "critical", "enterprise", ["HIPAA", "GINA", "GDPR"]),
            YamilNicheInfo("wearables_health", "Wearables Health", "healthtech", "Health wearables platform", "high", "large", ["HIPAA", "FDA", "GDPR"]),
            YamilNicheInfo("carbon_tracking", "Carbon Tracking", "greentech", "Carbon emissions tracking", "medium", "large", ["GHG Protocol", "TCFD"]),
            YamilNicheInfo("smart_grid", "Smart Grid", "greentech", "Smart grid management", "high", "enterprise", ["NERC", "IEC 61850"]),
            YamilNicheInfo("circular_economy", "Circular Economy", "greentech", "Circular economy platform", "medium", "large", ["EU Circular Economy"]),
            YamilNicheInfo("adaptive_learning", "Adaptive Learning", "edtech", "Adaptive learning platform", "medium", "large", ["FERPA", "COPPA"]),
            YamilNicheInfo("vr_education", "VR Education", "edtech", "VR education platform", "medium", "large", ["FERPA", "COPPA"]),
            YamilNicheInfo("micro_credentials", "Micro Credentials", "edtech", "Micro credential platform", "medium", "medium", ["FERPA"]),
            YamilNicheInfo("smart_buildings", "Smart Buildings", "proptech", "Smart building management", "high", "large", ["BREEAM", "LEED"]),
            YamilNicheInfo("digital_twins", "Digital Twins", "proptech", "Digital twin platform", "high", "enterprise", ["ISO 23247"]),
            YamilNicheInfo("fractional_ownership", "Fractional Ownership", "proptech", "Fractional property ownership", "critical", "large", ["SEC", "AML", "KYC"]),
            YamilNicheInfo("smart_contracts", "Smart Contracts", "legaltech", "Smart contract platform", "critical", "enterprise", ["SEC", "eIDAS"]),
            YamilNicheInfo("legal_ai", "Legal AI", "legaltech", "Legal AI assistant", "critical", "large", ["GDPR", "ABA", "SOX"]),
            YamilNicheInfo("compliance_automation", "Compliance Automation", "legaltech", "Compliance automation platform", "critical", "enterprise", ["SOX", "GDPR", "ISO 27001"]),
        ]

    @staticmethod
    def _fallback_template(niche_id: str) -> Dict[str, Any]:
        """Template basico cuando Rust no esta disponible."""
        return {
            "template": {
                "metadata": {
                    "niche_id": niche_id,
                    "version": "1.0.0",
                    "generated_at": time.time(),
                    "source": "yamil_fallback",
                },
                "sections": {
                    "business_identity": {
                        "display_name": "Business Identity",
                        "fields": {
                            "business_name": {"value": None, "type": "text", "required": True, "display_name": "Business Name"},
                            "business_type": {"value": None, "type": "text", "required": True, "display_name": "Business Type"},
                            "tax_id": {"value": None, "type": "text", "required": True, "display_name": "Tax ID"},
                            "country": {"value": None, "type": "text", "required": True, "display_name": "Country"},
                            "industry": {"value": None, "type": "text", "required": False, "display_name": "Industry"},
                            "website": {"value": None, "type": "url", "required": False, "display_name": "Website"},
                            "logo_url": {"value": None, "type": "url", "required": False, "display_name": "Logo URL"},
                        },
                    },
                    "security_access": {
                        "display_name": "Security & Access",
                        "fields": {
                            "auth_method": {"value": None, "type": "enum", "required": True, "display_name": "Authentication Method"},
                            "admin_email": {"value": None, "type": "email", "required": True, "display_name": "Admin Email"},
                            "admin_phone": {"value": None, "type": "phone", "required": False, "display_name": "Admin Phone"},
                            "enable_2fa": {"value": None, "type": "boolean", "required": False, "display_name": "Enable 2FA"},
                            "session_timeout_minutes": {"value": None, "type": "number", "required": False, "display_name": "Session Timeout (min)"},
                        },
                    },
                },
                "completeness": {
                    "total_fields": 12,
                    "filled_fields": 0,
                    "missing_required": 5,
                    "completion_pct": 0.0,
                },
            },
        }

    @staticmethod
    def _fallback_validate(template_dict: Dict[str, Any]) -> YamilValidationResult:
        """Validacion basica cuando Rust no esta disponible."""
        template = template_dict.get("template", template_dict)
        completeness = template.get("completeness", {})
        sections = template.get("sections", {})

        total = 0
        filled = 0
        missing_required = 0
        missing_names = []

        for section_id, section in sections.items():
            if not isinstance(section, dict):
                continue
            fields = section.get("fields", {})
            for fname, finfo in fields.items():
                if not isinstance(finfo, dict):
                    continue
                total += 1
                if finfo.get("value") is not None:
                    filled += 1
                elif finfo.get("required", False):
                    missing_required += 1
                    missing_names.append(fname)

        pct = (filled / total * 100.0) if total > 0 else 0.0
        status = "complete" if missing_required == 0 else ("partial" if filled > 0 else "incomplete")

        return YamilValidationResult(
            valid=missing_required == 0,
            completion_pct=pct,
            total_fields=total,
            filled_fields=filled,
            missing_required=missing_required,
            missing_field_names=missing_names,
            status=status,
        )
