"""
Block registry and niche template support mixin for TemplateEngine.
"""

from ._imports import logger, _LOAD_FAILED


class BlockNicheMixin:
    """Block registry and niche template methods for TemplateEngine."""

    def register_block(self, block):
        """Registra un bloque de codigo reutilizable."""
        self._blocks[block.name] = block
        logger.debug(f"TemplateEngine: Registered block '{block.name}' ({block.category})")

    def get_block(self, name: str):
        """Obtiene un bloque por nombre."""
        return self._blocks.get(name)

    def list_blocks(self, category: str = "") -> list:
        """Lista bloques disponibles, opcionalmente filtrados por categoria."""
        if category:
            return [b for b in self._blocks.values() if b.category == category]
        return list(self._blocks.values())

    def _get_niche_loader(self):
        """Obtiene el NicheLoader (lazy-loaded)."""
        if self._niche_loader is None:
            try:
                from ..niche_loader import NicheLoader
                self._niche_loader = NicheLoader()
                count = self._niche_loader.load_all()
                logger.info(f"TemplateEngine: NicheLoader loaded {count} niche templates")
            except ImportError:
                logger.warning("TemplateEngine: NicheLoader not available")
                self._niche_loader = _LOAD_FAILED
        return self._niche_loader if self._niche_loader is not _LOAD_FAILED else None

    def _get_dna_loader(self):
        """Obtiene el DNALoader (lazy-loaded)."""
        if self._dna_loader is None:
            try:
                from ..dna_loader import DNALoader
                self._dna_loader = DNALoader()
                counts = self._dna_loader.load_all()
                logger.info(f"TemplateEngine: DNALoader loaded {counts}")
            except ImportError:
                logger.warning("TemplateEngine: DNALoader not available")
                self._dna_loader = _LOAD_FAILED
        return self._dna_loader if self._dna_loader is not _LOAD_FAILED else None

    def get_dna(self):
        """Obtiene el DNALoader para acceso directo a las 4 plantillas maestras."""
        return self._get_dna_loader()

    def resolve_logic_for_niche(self, niche_name: str) -> list:
        """Resuelve módulos de lógica atómica para un nicho."""
        dna = self._get_dna_loader()
        if not dna:
            return []
        plan = self.get_niche_plan(niche_name)
        if not plan:
            return []
        modules = dna.resolve_modules_for_niche(niche_name, plan.blocks)
        return [
            {
                "id": m.id,
                "domain": m.domain,
                "description": m.description,
                "code_block": m.code_block,
                "dependencies": m.dependencies,
                "verification_rule": m.verification_rule,
            }
            for m in modules
        ]

    def validate_niche_code(self, code: str, niche_name: str = "") -> dict:
        """Valida código generado contra las gates de calidad del ADN."""
        dna = self._get_dna_loader()
        if not dna:
            return {"score": 0, "failed": [], "error": "DNALoader not available"}
        domain = ""
        if niche_name:
            niche = self._get_niche_loader()
            if niche:
                n = niche.get(niche_name)
                if n:
                    domain = n.domain
        return dna.validate_code(code, domain)

    def polish_output(self, text: str) -> str:
        """Transforma jerga técnica en lenguaje corporativo de élite."""
        dna = self._get_dna_loader()
        if dna:
            return dna.polish_text(text)
        return text

    def get_niche_plan(self, niche_name: str):
        """Obtiene un CompositionPlan para un nicho por nombre."""
        loader = self._get_niche_loader()
        if loader:
            return loader.get_plan(niche_name)
        return None

    def render_niche(self, niche_name: str) -> dict:
        """Renderiza una aplicacion completa a partir de un nicho predefinido."""
        plan = self.get_niche_plan(niche_name)
        if not plan:
            logger.error(f"TemplateEngine: Niche '{niche_name}' not found")
            return {}
        plan.blocks = self.resolve_dependencies(plan.blocks)
        return self.render_app(plan)

    def list_niches(self, domain: str = "") -> list:
        """Lista nichos disponibles, opcionalmente filtrados por dominio."""
        loader = self._get_niche_loader()
        if loader:
            return loader.list_niches(domain)
        return []

    def list_domains(self) -> list:
        """Lista todos los dominios de nichos disponibles."""
        loader = self._get_niche_loader()
        if loader:
            return loader.list_domains()
        return []

    def search_niches(self, query: str, limit: int = 10) -> list:
        """Busca nichos relevantes basado en una consulta."""
        loader = self._get_niche_loader()
        if loader:
            return loader.suggest_for_description(query)
        return []

    def suggest_niche_blocks(self, niche_name: str) -> list:
        """Sugiere bloques adicionales para un nicho basado en sus entities."""
        loader = self._get_niche_loader()
        if not loader:
            return []
        niche = loader.get(niche_name)
        if not niche:
            return []
        existing = set(niche.blocks)
        suggested = []
        entity_names = {e.get("name", "").lower() for e in niche.entities}
        if "jwt_auth" not in existing:
            suggested.append("jwt_auth")
        if "email_smtp" not in existing:
            if any(kw in entity_names for kw in ["user", "customer", "client", "patient", "student"]):
                suggested.append("email_smtp")
        if "backup_restore" not in existing:
            if niche.data_sensitivity in ("high", "critical"):
                suggested.append("backup_restore")
        if "rbac" not in existing and "jwt_auth" in existing:
            if niche.scale in ("enterprise", "large"):
                suggested.append("rbac")
        return suggested

    def resolve_dependencies(self, block_names: list) -> list:
        """Resuelve dependencias entre bloques y devuelve el orden correcto."""
        resolved = []
        visited = set()
        visiting = set()

        def visit(name: str):
            if name in visited:
                return
            if name in visiting:
                logger.warning(f"TemplateEngine: Circular dependency detected for {name}")
                return
            visiting.add(name)
            block = self._blocks.get(name)
            if block:
                for dep in block.dependencies:
                    visit(dep)
            visiting.discard(name)
            visited.add(name)
            resolved.append(name)

        for name in block_names:
            visit(name)
        return resolved

    def suggest_blocks(self, description: str) -> list:
        """Sugiere bloques relevantes basado en una descripcion."""
        desc_lower = description.lower()
        suggested = []
        for block in self._blocks.values():
            block_keywords = block.name.replace("_", " ").split()
            name_match = any(kw in desc_lower for kw in block_keywords)
            desc_keywords = block.description.lower().split()
            desc_match = any(kw in desc_lower for kw in desc_keywords if len(kw) > 3)
            category_keywords = {
                "business_logic": ["calcular", "logica", "procesar", "calculate", "logic", "business"],
                "integrations": ["email", "smtp", "api", "webhook", "stripe", "whatsapp", "telegram"],
                "auth": ["auth", "login", "usuario", "password", "jwt", "token", "rol"],
                "data": ["crud", "base de datos", "database", "migracion", "backup", "query"],
            }
            cat_keywords = category_keywords.get(block.category, [])
            cat_match = any(kw in desc_lower for kw in cat_keywords)
            if name_match or desc_match or cat_match:
                suggested.append(block.name)
        return self.resolve_dependencies(suggested)
