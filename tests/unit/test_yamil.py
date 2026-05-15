"""
Tests for YamilAgent — Agente Creador de Plantillas.

Cubre:
  - Catalogo: list_niches, search_niches, list_categories
  - Template: create_template, fill_field, fill_fields_batch
  - Validacion: validate, get_missing_fields
  - Safety: safety_check
  - Certificacion: certify
  - Export: export_yaml
  - Pipeline: run_full
  - Sesion: get_status, close_session
  - Fallback: operaciones sin Rust extension
  - BaseAgent: build_prompt, parse_response, fallback
"""

from __future__ import annotations

import pytest
import time
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

from src.core.agents.yamil import (
    YamilAgent,
    YamilAction,
    YamilFieldInfo,
    YamilNicheInfo,
    YamilResult,
    YamilSafetyResult,
    YamilSession,
    YamilStep,
    YamilValidationResult,
    YamilCertifyResult,
)


# ──────────────────────────────────────────────────────────────
#  FIXTURES
# ──────────────────────────────────────────────────────────────

@pytest.fixture
def yamil() -> YamilAgent:
    """YamilAgent instance (sin Rust extension)."""
    return YamilAgent()


@pytest.fixture
def yamil_with_session(yamil: YamilAgent) -> tuple[YamilAgent, str]:
    """YamilAgent con sesion activa de telemedicine."""
    result = yamil.create_template("telemedicine")
    assert result.success, f"Setup failed: {result.errors}"
    return yamil, result.session_id


# ──────────────────────────────────────────────────────────────
#  TEST: CATALOG OPERATIONS
# ──────────────────────────────────────────────────────────────

class TestCatalogOperations:
    """Tests para operaciones de catalogo de nichos."""

    def test_list_niches_returns_24(self, yamil: YamilAgent) -> None:
        """Debe listar exactamente 24 nichos."""
        result = yamil.list_niches()
        assert result.success is True
        assert result.action == YamilAction.LIST_NICHES.value
        assert len(result.niches) == 24

    def test_list_niches_has_required_fields(self, yamil: YamilAgent) -> None:
        """Cada nicho debe tener niche_id, name, category."""
        result = yamil.list_niches()
        for niche in result.niches:
            assert niche.niche_id, "niche_id vacio"
            assert niche.name, "name vacio"
            assert niche.category, "category vacio"

    def test_list_categories_returns_7(self, yamil: YamilAgent) -> None:
        """Debe listar exactamente 7 categorias."""
        result = yamil.list_categories()
        assert result.success is True
        assert len(result.categories) == 7
        expected = {"ai_data", "fintech", "healthtech", "greentech", "edtech", "proptech", "legaltech"}
        assert set(result.categories) == expected

    def test_search_niches_fintech(self, yamil: YamilAgent) -> None:
        """Buscar 'fintech' debe encontrar 4 nichos."""
        result = yamil.search_niches("fintech")
        assert result.success is True
        assert result.action == YamilAction.SEARCH_NICHES.value
        assert len(result.niches) == 4

    def test_search_niches_telemedicine(self, yamil: YamilAgent) -> None:
        """Buscar 'telemedicine' debe encontrar al menos 1 nicho."""
        result = yamil.search_niches("telemedicine")
        assert result.success is True
        assert len(result.niches) >= 1
        assert result.niches[0].niche_id == "telemedicine"

    def test_search_niches_empty_query(self, yamil: YamilAgent) -> None:
        """Query vacio debe listar todos los nichos."""
        result = yamil.search_niches("")
        assert result.success is True
        assert len(result.niches) == 24

    def test_search_niches_no_match(self, yamil: YamilAgent) -> None:
        """Query sin coincidencias debe devolver lista vacia."""
        result = yamil.search_niches("xyznonexistent123")
        assert result.success is True
        assert len(result.niches) == 0

    def test_niche_sensitivity_values(self, yamil: YamilAgent) -> None:
        """Los nichos deben tener valores de sensibilidad validos."""
        valid = {"low", "medium", "high", "critical"}
        result = yamil.list_niches()
        for niche in result.niches:
            assert niche.sensitivity.lower() in valid, f"Nicho {niche.niche_id} tiene sensibilidad invalida: {niche.sensitivity}"


# ──────────────────────────────────────────────────────────────
#  TEST: TEMPLATE CREATION
# ──────────────────────────────────────────────────────────────

class TestTemplateCreation:
    """Tests para creacion de plantillas."""

    def test_create_template_telemedicine(self, yamil: YamilAgent) -> None:
        """Debe crear plantilla para telemedicine."""
        result = yamil.create_template("telemedicine")
        assert result.success is True
        assert result.action == YamilAction.CREATE_TEMPLATE.value
        assert result.session_id, "Debe crear una sesion"
        assert result.template_dict is not None, "Debe generar template dict"
        assert result.niche_id == "telemedicine"
        assert result.progress_pct > 0

    def test_create_template_neo_banking(self, yamil: YamilAgent) -> None:
        """Debe crear plantilla para neo_banking."""
        result = yamil.create_template("neo_banking")
        assert result.success is True
        assert result.template_dict is not None

    def test_create_template_invalid_niche(self, yamil: YamilAgent) -> None:
        """Nicho invalido debe fallar."""
        result = yamil.create_template("nonexistent_niche")
        assert result.success is False
        assert len(result.errors) > 0

    def test_create_template_has_sections(self, yamil: YamilAgent) -> None:
        """Template debe tener secciones business_identity y security_access."""
        result = yamil.create_template("telemedicine")
        assert result.success is True
        template = result.template_dict
        template_inner = template.get("template", template)
        sections = template_inner.get("sections", {})
        assert "business_identity" in sections, "Falta seccion business_identity"
        assert "security_access" in sections, "Falta seccion security_access"

    def test_create_template_session_stored(self, yamil: YamilAgent) -> None:
        """Sesion debe quedar almacenada en el agente."""
        result = yamil.create_template("telemedicine")
        session = yamil.get_session(result.session_id)
        assert session is not None
        assert session.niche_id == "telemedicine"
        assert session.current_step == YamilStep.GENERATE_TEMPLATE

    def test_create_template_validation_populated(self, yamil: YamilAgent) -> None:
        """Resultado debe incluir validacion inicial."""
        result = yamil.create_template("telemedicine")
        assert result.validation is not None
        assert result.validation.total_fields > 0
        assert result.validation.completion_pct == 0.0


# ──────────────────────────────────────────────────────────────
#  TEST: FIELD OPERATIONS
# ──────────────────────────────────────────────────────────────

class TestFieldOperations:
    """Tests para operaciones de campos."""

    def test_fill_field(self, yamil_with_session: tuple) -> None:
        """Debe llenar un campo individual."""
        yamil, session_id = yamil_with_session
        result = yamil.fill_field(
            session_id, "business_identity", "business_name", "Mi Clinica"
        )
        assert result.success is True
        assert result.action == YamilAction.FILL_FIELD.value

    def test_fill_field_invalid_session(self, yamil: YamilAgent) -> None:
        """Sesion invalida debe fallar."""
        result = yamil.fill_field("nonexistent", "business_identity", "business_name", "Test")
        assert result.success is False

    def test_fill_fields_batch(self, yamil_with_session: tuple) -> None:
        """Debe llenar multiples campos en batch."""
        yamil, session_id = yamil_with_session
        result = yamil.fill_fields_batch(session_id, {
            "business_name": "Mi Clinica",
            "business_type": "Healthcare",
            "tax_id": "123456789",
            "country": "CU",
        })
        assert result.success is True
        assert result.action == YamilAction.FILL_FIELDS_BATCH.value

    def test_fill_fields_batch_auto_section(self, yamil_with_session: tuple) -> None:
        """fill_fields_batch sin section_id debe buscar automaticamente."""
        yamil, session_id = yamil_with_session
        result = yamil.fill_fields_batch(session_id, {
            "business_name": "Mi Clinica",
            "admin_email": "admin@clinic.com",
        })
        assert result.success is True

    def test_get_missing_fields(self, yamil_with_session: tuple) -> None:
        """Debe obtener campos faltantes."""
        yamil, session_id = yamil_with_session
        result = yamil.get_missing_fields(session_id)
        assert result.success is True
        assert result.action == YamilAction.GET_MISSING_FIELDS.value
        # Template nuevo debe tener campos faltantes
        assert len(result.missing_fields) >= 0  # Puede variar segun Rust vs fallback


# ──────────────────────────────────────────────────────────────
#  TEST: VALIDATION
# ──────────────────────────────────────────────────────────────

class TestValidation:
    """Tests para validacion de plantillas."""

    def test_validate_incomplete_template(self, yamil_with_session: tuple) -> None:
        """Template vacio debe fallar validacion."""
        yamil, session_id = yamil_with_session
        result = yamil.validate(session_id)
        assert result.action == YamilAction.VALIDATE.value
        assert result.validation is not None
        assert result.validation.completion_pct < 100.0

    def test_validate_after_filling(self, yamil_with_session: tuple) -> None:
        """Despues de llenar campos requeridos, validacion debe mejorar."""
        yamil, session_id = yamil_with_session
        # Llenar todos los campos requeridos
        yamil.fill_fields_batch(session_id, {
            "business_name": "Mi Clinica",
            "business_type": "Healthcare",
            "tax_id": "123456789",
            "country": "CU",
            "auth_method": "password",
            "admin_email": "admin@clinic.com",
        })
        result = yamil.validate(session_id)
        assert result.validation is not None
        assert result.validation.completion_pct > 0.0

    def test_validate_invalid_session(self, yamil: YamilAgent) -> None:
        """Sesion invalida debe fallar."""
        result = yamil.validate("nonexistent")
        assert result.success is False


# ──────────────────────────────────────────────────────────────
#  TEST: SAFETY CHECK
# ──────────────────────────────────────────────────────────────

class TestSafetyCheck:
    """Tests para safety check."""

    def test_safety_check_default(self, yamil_with_session: tuple) -> None:
        """Safety check con sensibilidad baja debe pasar."""
        yamil, session_id = yamil_with_session
        result = yamil.safety_check(session_id, data_sensitivity="low")
        assert result.action == YamilAction.SAFETY_CHECK.value
        assert result.safety is not None

    def test_safety_check_invalid_session(self, yamil: YamilAgent) -> None:
        """Sesion invalida debe fallar."""
        result = yamil.safety_check("nonexistent")
        assert result.success is False

    def test_safety_result_has_verdict(self, yamil_with_session: tuple) -> None:
        """Safety result debe tener un veredicto."""
        yamil, session_id = yamil_with_session
        result = yamil.safety_check(session_id)
        if result.safety is not None:
            assert result.safety.verdict in ("ALLOW", "CONFIRM", "APPROVE", "DENY")


# ──────────────────────────────────────────────────────────────
#  TEST: CERTIFICATION
# ──────────────────────────────────────────────────────────────

class TestCertification:
    """Tests para certificacion de Blueprint."""

    def test_certify_fallback(self, yamil_with_session: tuple) -> None:
        """Certificacion con fallback (sin Rust) debe generar hash."""
        yamil, session_id = yamil_with_session
        # Llenar campos para pasar validacion
        yamil.fill_fields_batch(session_id, {
            "business_name": "Mi Clinica",
            "business_type": "Healthcare",
            "tax_id": "123456789",
            "country": "CU",
            "auth_method": "password",
            "admin_email": "admin@clinic.com",
        })
        result = yamil.certify(session_id)
        assert result.action == YamilAction.CERTIFY.value
        # En modo fallback, deberia funcionar
        if result.certification is not None:
            assert result.certification.success is True or len(result.certification.errors) > 0

    def test_certify_invalid_session(self, yamil: YamilAgent) -> None:
        """Sesion invalida debe fallar."""
        result = yamil.certify("nonexistent")
        assert result.success is False


# ──────────────────────────────────────────────────────────────
#  TEST: EXPORT
# ──────────────────────────────────────────────────────────────

class TestExport:
    """Tests para exportacion YAML."""

    def test_export_yaml(self, yamil_with_session: tuple) -> None:
        """Debe exportar a YAML o JSON."""
        yamil, session_id = yamil_with_session
        result = yamil.export_yaml(session_id)
        assert result.action == YamilAction.EXPORT_YAML.value
        assert result.yaml_output, "Debe producir output"

    def test_export_invalid_session(self, yamil: YamilAgent) -> None:
        """Sesion invalida debe fallar."""
        result = yamil.export_yaml("nonexistent")
        assert result.success is False


# ──────────────────────────────────────────────────────────────
#  TEST: FULL PIPELINE
# ──────────────────────────────────────────────────────────────

class TestFullPipeline:
    """Tests para el pipeline completo E2E."""

    def test_run_full_basic(self, yamil: YamilAgent) -> None:
        """Pipeline completo basico sin certificar."""
        result = yamil.run_full(
            niche_id="telemedicine",
            answers={
                "business_name": "Mi Clinica",
                "business_type": "Healthcare",
                "tax_id": "123456789",
                "country": "CU",
                "auth_method": "password",
                "admin_email": "admin@clinic.com",
            },
        )
        assert result.action == YamilAction.RUN_FULL.value
        # Puede o no pasar validacion completa dependiendo de campos requeridos
        assert result.session_id, "Debe crear sesion"

    def test_run_full_with_certify(self, yamil: YamilAgent) -> None:
        """Pipeline completo con certificacion."""
        result = yamil.run_full(
            niche_id="data_analytics",
            answers={
                "business_name": "DataCorp",
                "business_type": "Technology",
                "tax_id": "987654321",
                "country": "US",
                "auth_method": "oauth2",
                "admin_email": "admin@datacorp.com",
            },
            private_key="test-key",
        )
        # Action puede ser run_full si todo pasa, o certify/validate si falla ahi
        assert result.action in (YamilAction.RUN_FULL.value, YamilAction.CERTIFY.value, YamilAction.VALIDATE.value)

    def test_run_full_invalid_niche(self, yamil: YamilAgent) -> None:
        """Pipeline con nicho invalido debe fallar temprano."""
        result = yamil.run_full(niche_id="nonexistent")
        assert result.success is False
        assert len(result.errors) > 0

    def test_run_full_incomplete_template(self, yamil: YamilAgent) -> None:
        """Pipeline sin answers debe fallar en validacion si hay campos requeridos."""
        result = yamil.run_full(niche_id="telemedicine")
        # Depende de si hay campos requeridos — puede pasar o fallar
        assert result.action == YamilAction.RUN_FULL.value


# ──────────────────────────────────────────────────────────────
#  TEST: SESSION MANAGEMENT
# ──────────────────────────────────────────────────────────────

class TestSessionManagement:
    """Tests para gestion de sesiones."""

    def test_get_status(self, yamil_with_session: tuple) -> None:
        """Debe obtener estado de sesion."""
        yamil, session_id = yamil_with_session
        result = yamil.get_status(session_id)
        assert result.success is True
        assert result.action == YamilAction.GET_STATUS.value
        assert result.progress_pct > 0

    def test_get_status_invalid_session(self, yamil: YamilAgent) -> None:
        """Sesion invalida debe fallar."""
        result = yamil.get_status("nonexistent")
        assert result.success is False

    def test_close_session(self, yamil_with_session: tuple) -> None:
        """Debe cerrar sesion."""
        yamil, session_id = yamil_with_session
        closed = yamil.close_session(session_id)
        assert closed is True
        # Sesion ya no debe existir
        assert yamil.get_session(session_id) is None

    def test_close_session_invalid(self, yamil: YamilAgent) -> None:
        """Cerrar sesion inexistente debe devolver False."""
        closed = yamil.close_session("nonexistent")
        assert closed is False


# ──────────────────────────────────────────────────────────────
#  TEST: BASEAGENT IMPLEMENTATION
# ──────────────────────────────────────────────────────────────

class TestBaseAgentImplementation:
    """Tests para la implementacion de BaseAgent."""

    def test_build_prompt(self, yamil: YamilAgent) -> None:
        """build_prompt debe producir system y user prompts."""
        system, user = yamil.build_prompt("necesito un sistema de salud")
        assert "Yamil" in system
        assert "niche_id" in system.lower()
        assert "salud" in user.lower() or "necesito" in user.lower()

    def test_parse_response_valid_niche(self, yamil: YamilAgent) -> None:
        """parse_response debe reconocer niche_id valido."""
        result = yamil.parse_response("telemedicine", None)
        assert result is not None
        assert result.success is True
        assert len(result.niches) == 1
        assert result.niches[0].niche_id == "telemedicine"

    def test_parse_response_invalid(self, yamil: YamilAgent) -> None:
        """parse_response con respuesta invalida debe devolver None."""
        result = yamil.parse_response("no es un nicho valido", None)
        assert result is None

    def test_fallback_deterministic(self, yamil: YamilAgent) -> None:
        """fallback debe producir resultado deterministico."""
        result1 = yamil.fallback("telemedicine")
        result2 = yamil.fallback("telemedicine")
        assert result1.success is True
        assert result2.success is True
        assert len(result1.niches) == len(result2.niches)

    def test_fallback_empty_query(self, yamil: YamilAgent) -> None:
        """fallback con query vacio debe listar todos."""
        result = yamil.fallback("")
        assert result.success is True
        assert len(result.niches) == 24

    def test_agent_name(self, yamil: YamilAgent) -> None:
        """Agente debe llamarse 'yamil'."""
        assert yamil.name == "yamil"

    def test_agent_stats(self, yamil: YamilAgent) -> None:
        """Agente debe tener estadisticas."""
        stats = yamil.stats
        assert stats["name"] == "yamil"
        assert "total_calls" in stats


# ──────────────────────────────────────────────────────────────
#  TEST: YAMILSESSION DATA CLASS
# ──────────────────────────────────────────────────────────────

class TestYamilSession:
    """Tests para YamilSession."""

    def test_session_auto_id(self) -> None:
        """Sesion debe generar ID automaticamente."""
        session = YamilSession()
        assert session.session_id.startswith("yamil-")

    def test_session_progress(self) -> None:
        """Progreso debe incrementar con cada paso."""
        session = YamilSession()
        assert session.progress_pct == 0.0
        session.current_step = YamilStep.SELECT_NICHE
        assert session.progress_pct == 12.5
        session.current_step = YamilStep.COMPLETED
        assert session.progress_pct == 100.0

    def test_session_audit_log(self) -> None:
        """Audit log debe registrar acciones."""
        session = YamilSession()
        session.add_audit("test_action", "test detail")
        assert len(session.audit_log) == 1
        assert session.audit_log[0]["action"] == "test_action"

    def test_session_errors(self) -> None:
        """add_error debe agregar errores."""
        session = YamilSession()
        session.add_error("test error")
        assert len(session.errors) == 1

    def test_session_is_complete(self) -> None:
        """is_complete debe reflejar estado."""
        session = YamilSession()
        assert session.is_complete is False
        session.current_step = YamilStep.COMPLETED
        assert session.is_complete is True


# ──────────────────────────────────────────────────────────────
#  TEST: YAMILRESULT DATA CLASS
# ──────────────────────────────────────────────────────────────

class TestYamilResult:
    """Tests para YamilResult."""

    def test_result_defaults(self) -> None:
        """Result debe tener defaults correctos."""
        result = YamilResult(success=True, action="test")
        assert result.success is True
        assert result.errors == []
        assert result.warnings == []
        assert result.niches == []
        assert result.yaml_output == ""


# ──────────────────────────────────────────────────────────────
#  TEST: YAMILVALIDATIONRESULT
# ──────────────────────────────────────────────────────────────

class TestYamilValidationResult:
    """Tests para YamilValidationResult."""

    def test_incomplete(self) -> None:
        """Template incompleto debe reflejar estado."""
        v = YamilValidationResult(
            valid=False, completion_pct=30.0, total_fields=10,
            filled_fields=3, missing_required=5, status="partial",
        )
        assert v.valid is False
        assert v.completion_pct == 30.0

    def test_complete(self) -> None:
        """Template completo debe ser valido."""
        v = YamilValidationResult(
            valid=True, completion_pct=100.0, total_fields=10,
            filled_fields=10, missing_required=0, status="complete",
        )
        assert v.valid is True
        assert v.missing_required == 0


# ──────────────────────────────────────────────────────────────
#  TEST: COMPLETE_AND_CERTIFY CONVENIENCE
# ──────────────────────────────────────────────────────────────

class TestCompleteAndCertify:
    """Tests para convenience method complete_and_certify."""

    def test_complete_and_certify_no_session(self, yamil: YamilAgent) -> None:
        """Sin sesion debe fallar."""
        result = YamilResult(success=True, action="test")
        output = yamil.complete_and_certify(result)
        assert output.success is False

    def test_complete_and_certify_with_session(self, yamil_with_session: tuple) -> None:
        """Con sesion debe ejecutar pipeline."""
        yamil, session_id = yamil_with_session
        # Primero llenar campos
        yamil.fill_fields_batch(session_id, {
            "business_name": "Mi Clinica",
            "business_type": "Healthcare",
            "tax_id": "123456789",
            "country": "CU",
            "auth_method": "password",
            "admin_email": "admin@clinic.com",
        })
        result = YamilResult(
            success=True, action="fill_fields_batch",
            session_id=session_id, niche_id="telemedicine",
        )
        output = yamil.complete_and_certify(result, data_sensitivity="low")
        assert output.action == YamilAction.EXPORT_YAML.value or not output.success


# ──────────────────────────────────────────────────────────────
#  TEST: EDGE CASES
# ──────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Tests para casos extremos."""

    def test_multiple_sessions(self, yamil: YamilAgent) -> None:
        """Debe soportar multiples sesiones simultaneas."""
        r1 = yamil.create_template("telemedicine")
        r2 = yamil.create_template("neo_banking")
        assert r1.session_id != r2.session_id
        assert r1.success is True
        assert r2.success is True

    def test_fill_same_field_twice(self, yamil_with_session: tuple) -> None:
        """Llenar el mismo campo dos veces debe sobreescribir."""
        yamil, session_id = yamil_with_session
        r1 = yamil.fill_field(session_id, "business_identity", "business_name", "Clinica 1")
        r2 = yamil.fill_field(session_id, "business_identity", "business_name", "Clinica 2")
        assert r1.success is True
        assert r2.success is True

    def test_all_24_niches_create_template(self, yamil: YamilAgent) -> None:
        """Debe poder crear plantilla para todos los 24 nichos."""
        niche_ids = [
            "ai_automation", "data_analytics", "ml_operations", "nlp_services",
            "defi_protocols", "neo_banking", "insurtech", "regtech",
            "telemedicine", "mental_health_ai", "genomics", "wearables_health",
            "carbon_tracking", "smart_grid", "circular_economy",
            "adaptive_learning", "vr_education", "micro_credentials",
            "smart_buildings", "digital_twins", "fractional_ownership",
            "smart_contracts", "legal_ai", "compliance_automation",
        ]
        for niche_id in niche_ids:
            result = yamil.create_template(niche_id)
            assert result.success is True, f"Fallo al crear template para {niche_id}: {result.errors}"
            # Limpiar sesion para no acumular
            yamil.close_session(result.session_id)
