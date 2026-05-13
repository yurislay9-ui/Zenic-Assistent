"""
ZENIC-AGENTS - AppGenerator Core

AppGenerator class (init, generate_app, main orchestration).
Combines all mixins: FileGeneratorMixin, ServiceGeneratorMixin,
TemplateGeneratorMixin, UtilsMixin.
"""

import os
import time
import secrets
import logging

from src.core.app_gen_parts.types import GeneratedProject, PROJECTS_DIR
from src.core.app_gen_parts.file_generators import FileGeneratorMixin
from src.core.app_gen_parts.service_generators import ServiceGeneratorMixin
from src.core.app_gen_parts.template_generators import TemplateGeneratorMixin
from src.core.app_gen_parts.utils import UtilsMixin

logger = logging.getLogger(__name__)


class AppGenerator(FileGeneratorMixin, ServiceGeneratorMixin, TemplateGeneratorMixin, UtilsMixin):
    """
    Generador de aplicaciones completas para PYMEs.

    Genera proyectos Python reales y ejecutables usando templates
    Jinja2 externos + bloques de logica componibles, personalizados
    por el ThinkingEngine.
    """

    def __init__(self, thinking_engine=None, template_engine=None):
        self._thinking = thinking_engine
        self._template_engine = template_engine
        os.makedirs(PROJECTS_DIR, exist_ok=True)

        # Lazy-init template engine if not provided
        if self._template_engine is None:
            try:
                from src.core.template_engine import TemplateEngine
                self._template_engine = TemplateEngine()
            except ImportError:
                logger.warning("AppGenerator: TemplateEngine not available, using legacy f-string generation")

    # ================================================================
    #  MAIN ENTRY POINT
    # ================================================================

    def generate_app(self, request: str, project_name: str = "",
                     output_dir: str = "") -> GeneratedProject:
        """
        Genera una aplicación completa. Usa TemplateEngine si disponible,
        sino usa el generador legacy con f-strings.
        """
        if self._template_engine:
            return self.generate_app_v2(request, project_name, output_dir)
        return self.generate_app_legacy(request, project_name, output_dir)

    def generate_app_v2(self, request: str, project_name: str = "",
                        output_dir: str = "") -> GeneratedProject:
        """
        Genera una aplicación usando TemplateEngine + bloques componibles.

        Estrategia: BLOCKS + AI ASSEMBLER
          1. ThinkingEngine analiza requisitos y planifica
          2. TemplateEngine sugiere bloques relevantes
          3. Bloques se componen en la app final
          4. Resultado: codigo funcional, no stubs
        """
        start_time = time.time()

        # Step 1: Plan generation
        if self._thinking:
            plan = self._thinking.plan_generation(request)
        else:
            plan = self._fallback_plan(request)

        # Step 2: Suggest blocks based on description
        suggested_blocks = self._template_engine.suggest_blocks(request)

        # Step 3: Generate project name and output dir
        if not project_name:
            project_name = self._generate_project_name(plan.template_type, request)
        if not output_dir:
            output_dir = os.path.join(PROJECTS_DIR, project_name)
        os.makedirs(output_dir, exist_ok=True)

        # Step 4: Build composition plan
        from src.core.template_engine import CompositionPlan
        composition = CompositionPlan(
            base_template="apps/base",
            app_template=plan.template_type if plan.template_type != "generic" else "",
            blocks=suggested_blocks,
            variables={
                "project_name": project_name,
                "app_name": project_name,
                "template_type": plan.template_type,
                "db_name": project_name + ".db",
                "port": plan.config_vars.get("port", 8000),
                "secret_key": plan.config_vars.get("secret_key", secrets.token_hex(32)),
                "debug": True,
                "version": "1.0.0",
            },
            entities=plan.entities,
        )

        # Step 5: Render all files via TemplateEngine
        generated = GeneratedProject(
            name=project_name,
            template_type=plan.template_type,
            path=output_dir,
            entities=plan.entities,
            endpoints=plan.endpoints,
        )

        try:
            files = self._template_engine.render_app(composition)

            for filepath, content in files.items():
                full_path = os.path.join(output_dir, filepath)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)
                generated.files.append(filepath)

            generated.main_file = "main.py"
            generated.status = "generated"
            generated.generation_time_s = time.time() - start_time

            logger.info(f"AppGenerator v2: Generated {project_name} with {len(files)} files, {len(suggested_blocks)} blocks in {generated.generation_time_s:.1f}s")

        except Exception as e:
            generated.status = "failed"
            generated.error = str(e)
            generated.generation_time_s = time.time() - start_time
            logger.error(f"AppGenerator v2: Failed to generate {project_name}: {e}")

        return generated

    def generate_app_legacy(self, request: str, project_name: str = "",
                            output_dir: str = "") -> GeneratedProject:
        """
        Genera una aplicación completa a partir de una descripción en lenguaje natural.

        Args:
            request: Descripción de lo que el cliente necesita
            project_name: Nombre del proyecto (opcional, se genera si no se da)
            output_dir: Directorio de salida (opcional, default: ~/.zenic_agents/projects/)

        Returns:
            GeneratedProject con todos los archivos generados
        """
        start_time = time.time()

        # Step 1: Use ThinkingEngine to plan the generation
        if self._thinking:
            plan = self._thinking.plan_generation(request)
        else:
            plan = self._fallback_plan(request)

        # Step 2: Generate project name
        if not project_name:
            project_name = self._generate_project_name(plan.template_type, request)

        # Step 3: Setup output directory
        if not output_dir:
            output_dir = os.path.join(PROJECTS_DIR, project_name)
        os.makedirs(output_dir, exist_ok=True)

        # Step 4: Generate all project files
        generated = GeneratedProject(
            name=project_name,
            template_type=plan.template_type,
            path=output_dir,
            entities=plan.entities,
            endpoints=plan.endpoints,
        )

        try:
            # Generate core files
            files = {}

            files["requirements.txt"] = self._gen_requirements(plan)
            files["database.py"] = self._gen_database(plan, project_name)
            files["models.py"] = self._gen_models(plan, project_name)
            files["services.py"] = self._gen_services(plan, project_name)
            files["main.py"] = self._gen_main(plan, project_name)
            files["config.py"] = self._gen_config(plan, project_name)

            # Generate HTML templates
            os.makedirs(os.path.join(output_dir, "templates"), exist_ok=True)
            files["templates/base.html"] = self._gen_base_template(plan, project_name)
            files["templates/dashboard.html"] = self._gen_dashboard_template(plan, project_name)
            files["templates/list.html"] = self._gen_list_template(plan, project_name)
            files["templates/form.html"] = self._gen_form_template(plan, project_name)

            # Generate static files
            os.makedirs(os.path.join(output_dir, "static"), exist_ok=True)
            files["static/style.css"] = self._gen_css(plan, project_name)

            # Generate README
            files["README.md"] = self._gen_readme(plan, project_name)

            # Write all files
            for filepath, content in files.items():
                full_path = os.path.join(output_dir, filepath)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)
                generated.files.append(filepath)

            generated.main_file = "main.py"
            generated.status = "generated"
            generated.generation_time_s = time.time() - start_time

            logger.info(f"AppGenerator: Generated {project_name} with {len(files)} files in {generated.generation_time_s:.1f}s")

        except Exception as e:
            generated.status = "failed"
            generated.error = str(e)
            generated.generation_time_s = time.time() - start_time
            logger.error(f"AppGenerator: Failed to generate {project_name}: {e}")

        return generated
