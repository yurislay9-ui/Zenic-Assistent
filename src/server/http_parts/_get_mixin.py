"""
GET endpoint mixin for ZenicHTTPHandler.
"""

import time

from ._imports import (
    logger, HAS_Z3, urlparse, parse_qs, _run_async,
)
from src.core.shared._version import ZENIC_VERSION, ZENIC_FULL_NAME


class GetMixin:
    """GET endpoint handlers for ZenicHTTPHandler."""

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == '/v1/models':
            self._send_json({
                "object": "list",
                "data": [{
                    "id": "zenic-agents",
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "zenic-local"
                }]
            })
        elif path == '/':
            self._handle_root()
        elif path == '/health':
            self._handle_health()
        elif path == '/v1/projects':
            self._handle_list_projects(params)
        elif path == '/v1/automations':
            self._handle_list_automations()
        elif path == '/v1/templates':
            self._handle_list_templates()
        elif path == '/v1/niches':
            self._handle_list_niches(params)
        elif path == '/v1/niches/domains':
            self._handle_list_domains()
        elif path == '/v1/niches/search':
            self._handle_search_niches(params)
        elif path == '/v1/system/status':
            self._handle_system_status()
        elif path == '/v1/intelligence/status':
            self._handle_intelligence_status()
        elif path == '/v1/system/power-mode':
            self._handle_power_mode()
        elif path == '/v1/system/context-index':
            self._handle_context_index(params)
        elif path == '/v1/system/auto-evolve':
            self._handle_auto_evolve(params)
        elif path == '/v1/dna/modules':
            self._handle_dna_modules(params)
        elif path == '/v1/dna/domain-rules':
            self._handle_dna_domain_rules(params)
        else:
            self._send_json({"error": "Not found"}, status=404)

    def _handle_root(self):
        """Info general del servidor."""
        solver_name = "Z3" if HAS_Z3 else "AC-3"
        gov = self.governor
        res_status = gov.get_status() if gov else {}
        version_suffix = f"-{self.platform_tag}" if self.platform_tag else ""
        features = [
            "MCTS", f"{solver_name}_Solver", "Timeout_Enforcement",
            "Theorem_Cache", "Skeleton_Hash", "K_Path_Limiting",
            "Symbolic_Execution", "Abortive_Protocol",
            "Partial_Reasoning", "Contextual_CodeGen",
            "ThinkingEngine", "AppGenerator", "AutomationEngine",
            "SchemaDesigner", "SmartMemory_Enhanced",
            "ReasoningEngine", "ChainValidator", "ChainExecutor",
        ]
        if gov:
            features.append("Resource_Governor")
        response = {
            "status": "active",
            "model": "zenic-agents",
            "version": f"{ZENIC_VERSION}{version_suffix}",
            "endpoints": [
                "/v1/chat/completions", "/v1/models", "/health",
                "/v1/generate/app", "/v1/generate/automation", "/v1/generate/niche",
                "/v1/design/schema", "/v1/think", "/v1/reason",
                "/v1/chain/validate", "/v1/chain/execute",
                "/v1/projects", "/v1/automations",
                "/v1/niches", "/v1/niches/domains", "/v1/niches/search",
                "/v1/templates", "/v1/system/status",
                "/v1/intelligence/status",
            ],
            "pipeline_levels": 8,
            "solver": solver_name,
            "features": features,
            "description": f"{ZENIC_FULL_NAME} - Local Surgical AI Engine ({solver_name}) + App & Automation Generator",
        }
        if self.platform_tag:
            response["platform"] = self.platform_tag
        if res_status:
            response["resources"] = res_status
        self._send_json(response)

    def _handle_health(self):
        """Health check con info de recursos si governor disponible."""
        solver_name = "Z3" if HAS_Z3 else "AC-3"
        gov = self.governor
        health = {
            "status": "healthy",
            "solver": solver_name,
            "has_z3": HAS_Z3,
            "mode": "hybrid_lazy",
        }
        if self.start_time:
            health["uptime_s"] = int(time.time() - self.start_time)
        if gov:
            health["resources"] = gov.get_status()
            if gov.is_ram_critical():
                health["status"] = "degraded"
                health["reason"] = f"RAM critical: {gov.ram_usage_mb:.0f}MB"
        if hasattr(self.orchestrator, '_model_mgr'):
            health["models"] = self.orchestrator._model_mgr.get_status()
        self._send_json(health)

    def _handle_list_projects(self, params):
        """GET /v1/projects - Lista proyectos generados."""
        try:
            status_filter = params.get("status", [""])[0]
            projects = _run_async(self.orchestrator.list_projects(status_filter))
            self._send_json({"projects": projects, "total": len(projects)})
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_list_automations(self):
        """GET /v1/automations - Lista automatizaciones."""
        try:
            automations = _run_async(self.orchestrator.list_automations())
            self._send_json({"automations": automations, "total": len(automations)})
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_list_templates(self):
        """GET /v1/templates - Lista templates disponibles."""
        try:
            from src.core.app_generator import AppGenerator
            templates = AppGenerator.list_templates()
            try:
                from src.core.template_engine import TemplateEngine
                engine = TemplateEngine()
                templates["niche_templates"] = engine.list_niches()
                templates["niche_domains"] = engine.list_domains()
            except Exception as e:
                logger.debug("HTTP: TemplateEngine niche listing failed: %s", e)
            self._send_json(templates)
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_list_niches(self, params):
        """GET /v1/niches - Lista nichos disponibles."""
        try:
            domain = params.get("domain", [""])[0]
            from src.core.template_engine import TemplateEngine
            engine = TemplateEngine()
            niches = engine.list_niches(domain)
            result = []
            for name in niches:
                plan = engine.get_niche_plan(name)
                if plan:
                    result.append({
                        "name": name,
                        "entities": len(plan.entities),
                        "blocks": plan.blocks,
                    })
            self._send_json({"niches": result, "total": len(result), "domain": domain or "all"})
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_list_domains(self):
        """GET /v1/niches/domains - Lista dominios de nichos."""
        try:
            from src.core.template_engine import TemplateEngine
            engine = TemplateEngine()
            domains = engine.list_domains()
            result = []
            for d in domains:
                niches = engine.list_niches(d)
                result.append({"domain": d, "niche_count": len(niches), "niches": niches})
            self._send_json({"domains": result, "total": len(result)})
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_search_niches(self, params):
        """GET /v1/niches/search - Buscar nichos por descripcion."""
        try:
            query = params.get("q", [""])[0]
            if not query:
                self._send_json({"error": "Missing 'q' parameter"}, status=400)
                return
            from src.core.template_engine import TemplateEngine
            engine = TemplateEngine()
            results = engine.search_niches(query)
            self._send_json({"results": results, "total": len(results), "query": query})
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_system_status(self):
        """GET /v1/system/status - Estado completo del sistema."""
        try:
            status = _run_async(self.orchestrator.get_system_status())
            self._send_json(status)
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_intelligence_status(self):
        """GET /v1/intelligence/status - Estado de inteligencia (Phase 8)."""
        try:
            status = _run_async(self.orchestrator.get_intelligence_status())
            self._send_json(status)
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_power_mode(self):
        """GET /v1/system/power-mode - Estado del modo Low-Power Sequential."""
        try:
            lpm = getattr(self.orchestrator, '_low_power_mode', None)
            if lpm:
                self._send_json(lpm.stats)
            else:
                self._send_json({"mode": "unavailable", "reason": "LowPowerSequentialMode not initialized"})
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_context_index(self, params=None):
        """GET /v1/system/context-index - Estado del índice de Context Pointers."""
        try:
            cpe = getattr(self.orchestrator, '_context_pointer_engine', None)
            if cpe:
                query = (params or {}).get("q", [""])[0] if params else ""
                if query:
                    pointers = cpe.search(query, top_k=10)
                    result = {
                        "stats": cpe.stats,
                        "query": query,
                        "results": [p.to_model_context() for p in pointers],
                    }
                else:
                    result = cpe.stats
                self._send_json(result)
            else:
                self._send_json({"status": "unavailable", "reason": "ContextPointerEngine not initialized"})
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_auto_evolve(self, params):
        """GET /v1/system/auto-evolve - Estado del Auto-Scraping YAML."""
        try:
            cron = getattr(self.orchestrator, '_niche_cron', None)
            updater = getattr(self.orchestrator, '_niche_auto_scraper', None)
            result = {
                "auto_scraper": updater.stats if updater else {"status": "unavailable"},
                "cron_scheduler": cron.stats if cron else {"status": "unavailable"},
            }
            self._send_json(result)
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_dna_modules(self, params):
        """GET /v1/dna/modules - Listar módulos de lógica atómica."""
        try:
            from src.core.dna_loader import get_dna_loader
            dna = get_dna_loader()
            domain = params.get("domain", [""])[0]
            query = params.get("q", [""])[0]
            if query:
                modules = dna.search_modules(query, limit=20)
            elif domain:
                modules = dna.get_modules_by_domain(domain)
            else:
                modules = list(dna._logic_modules.values())
            result = [
                {"id": m.id, "domain": m.domain, "description": m.description,
                 "dependencies": m.dependencies, "verification_rule": m.verification_rule}
                for m in modules
            ]
            self._send_json({"modules": result, "total": len(result)})
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_dna_domain_rules(self, params):
        """GET /v1/dna/domain-rules - Obtener reglas de negocio por industria."""
        try:
            from src.core.dna_loader import get_dna_loader
            dna = get_dna_loader()
            industry = params.get("industry", [""])[0]
            if industry:
                rules = dna.get_domain_rules(industry)
                if rules:
                    self._send_json({
                        "industry": rules.name,
                        "display_name": rules.display_name,
                        "mandatory_logic": rules.mandatory_logic,
                        "compliance": rules.compliance_requirements,
                        "invariants": rules.business_invariants,
                    })
                else:
                    self._send_json({"error": f"Industry '{industry}' not found"}, status=404)
            else:
                industries = [{"name": r.name, "display_name": r.display_name,
                               "mandatory_count": len(r.mandatory_logic)}
                              for r in dna._domain_rules.values()]
                self._send_json({"industries": industries, "total": len(industries)})
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)
