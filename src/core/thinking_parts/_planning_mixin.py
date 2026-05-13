"""
Planning methods mixin for ThinkingEngine — plan_generation, identify_template,
identify_entities, generate_endpoints, identify_modules, default_entities, generate_config.
"""

import re
import json
import os

from ._imports import (
    logger, APP_TEMPLATES, AUTOMATION_TEMPLATES,
    MAX_PLAN_TOKENS, GenerationPlan,
)


class PlanningMixin:
    """Planning and template selection methods for ThinkingEngine."""

    def plan_generation(self, request: str) -> GenerationPlan:
        """Descompone un request de generación en un plan detallado."""
        template = self._identify_template(request)
        entities = self._identify_entities(request, template)
        endpoints = self._generate_endpoints(entities, template)
        modules = self._identify_modules(template)
        config = self._generate_config(template, entities)

        confidence = 0.7 if template != "generic" else 0.3

        return GenerationPlan(
            template_type=template,
            modules=modules,
            entities=entities,
            endpoints=endpoints,
            automations=[],
            config_vars=config,
            confidence=confidence,
            source="thinking" if self._ai and self._ai.is_loaded else "fallback",
        )

    def _identify_template(self, request: str) -> str:
        """Identifica el tipo de template más adecuado para el request."""
        if self._semantic and self._semantic.is_loaded:
            best_template = None
            best_sim = 0.0
            for tmpl in APP_TEMPLATES + AUTOMATION_TEMPLATES:
                sim = self._semantic.similarity_text(request, tmpl.replace("_", " "))
                if sim > best_sim:
                    best_sim = sim
                    best_template = tmpl
            if best_sim > 0.4:
                return best_template

        template_list = ", ".join(APP_TEMPLATES + AUTOMATION_TEMPLATES)
        answer = self._call_with_context(
            system_prompt=f"Select the best template type for this request. Reply with ONLY one of: {template_list}",
            user_prompt=request,
            max_tokens=100,
            query=request,
        )
        if answer:
            clean = answer.lower().strip().replace(" ", "_").replace("-", "_")
            for tmpl in APP_TEMPLATES + AUTOMATION_TEMPLATES:
                if tmpl in clean:
                    return tmpl

        request_lower = request.lower()
        keyword_map = {
            "web_api": ["api", "rest", "endpoint", "servidor", "server"],
            "crud_dashboard": ["dashboard", "panel", "tabla", "gestionar", "manage"],
            "inventory": ["inventario", "stock", "almacen", "inventory", "warehouse"],
            "invoice_billing": ["factura", "invoice", "billing", "cobro", "pago"],
            "crm": ["cliente", "customer", "crm", "ventas", "sales"],
            "task_manager": ["tarea", "task", "proyecto", "project", "kanban"],
            "email_automation": ["email", "correo", "notificacion", "notification"],
            "data_pipeline": ["pipeline", "etl", "datos", "data", "procesar"],
            "report_generator": ["reporte", "report", "informe", "estadistica"],
            "auth_system": ["auth", "login", "usuario", "user", "contraseña"],
            "notification_service": ["notificacion", "alerta", "notification", "alert"],
            "scheduler": ["horario", "schedule", "calendar", "agenda", "cita"],
            "chatbot_service": ["chatbot", "chat", "bot", "asistente"],
            "email_sender": ["enviar email", "send email", "mailing"],
            "data_sync": ["sincronizar", "sync", "integrar"],
            "webhook_handler": ["webhook", "callback", "evento"],
            "scheduled_report": ["reporte automatico", "scheduled report"],
            "database_backup": ["backup", "respaldo", "copia"],
            "api_monitor": ["monitor", "vigilar", "health check"],
            "social_media_poster": ["social media", "redes sociales", "post"],
            "invoice_generator": ["generar factura", "invoice generator"],
            "notification_dispatcher": ["dispatch", "enviar notificacion"],
        }
        for tmpl, keywords in keyword_map.items():
            if any(kw in request_lower for kw in keywords):
                return tmpl
        return "generic"

    def _identify_entities(self, request: str, template: str) -> list:
        """Identifica las entidades de negocio del request."""
        answer = self._call_with_context(
            system_prompt='Extract business entities from the request. Reply with JSON array: [{"name":"EntityName","fields":["field1:type","field2:type"]}]. Types: str, int, float, bool, datetime, list, dict.',
            user_prompt=request,
            max_tokens=MAX_PLAN_TOKENS,
            query=request,
        )
        if answer:
            try:
                match = re.search(r'\[.*\]', answer, re.DOTALL)
                if match:
                    entities = json.loads(match.group())
                    if isinstance(entities, list) and entities:
                        return entities
            except (json.JSONDecodeError, ValueError):
                pass
        return self._default_entities(template)

    def _generate_endpoints(self, entities: list, template: str) -> list:
        """Genera endpoints CRUD para las entidades identificadas."""
        endpoints = []
        base_endpoints = {
            "web_api": [
                {"method": "GET", "path": "/health", "desc": "Health check"},
                {"method": "GET", "path": "/api/info", "desc": "API info"},
            ],
            "crm": [{"method": "GET", "path": "/api/dashboard", "desc": "Dashboard stats"}],
            "inventory": [{"method": "GET", "path": "/api/stock/summary", "desc": "Stock summary"}],
            "invoice_billing": [{"method": "POST", "path": "/api/invoices/generate", "desc": "Generate invoice"}],
        }
        endpoints.extend(base_endpoints.get(template, []))
        for entity in entities[:5]:
            name = entity.get("name", "item").lower()
            endpoints.extend([
                {"method": "GET", "path": f"/api/{name}s", "desc": f"List all {name}s"},
                {"method": "GET", "path": f"/api/{name}s/{{id}}", "desc": f"Get {name} by ID"},
                {"method": "POST", "path": f"/api/{name}s", "desc": f"Create {name}"},
                {"method": "PUT", "path": f"/api/{name}s/{{id}}", "desc": f"Update {name}"},
                {"method": "DELETE", "path": f"/api/{name}s/{{id}}", "desc": f"Delete {name}"},
            ])
        return endpoints

    def _identify_modules(self, template: str) -> list:
        """Identifica los módulos necesarios según el template."""
        template_modules = {
            "web_api": ["models", "api", "services", "config"],
            "crud_dashboard": ["models", "api", "services", "templates", "static"],
            "inventory": ["models", "api", "services", "reports", "templates"],
            "invoice_billing": ["models", "api", "services", "reports", "templates", "pdf"],
            "crm": ["models", "api", "services", "reports", "templates", "static"],
            "task_manager": ["models", "api", "services", "templates", "websocket"],
            "email_automation": ["models", "services", "templates", "scheduler"],
            "data_pipeline": ["models", "services", "etl", "config"],
            "report_generator": ["models", "services", "reports", "templates"],
            "auth_system": ["models", "api", "services", "middleware"],
            "notification_service": ["models", "services", "channels", "scheduler"],
            "file_manager": ["models", "api", "services", "storage"],
            "scheduler": ["models", "api", "services", "calendar"],
            "chatbot_service": ["models", "api", "services", "nlp"],
            "email_sender": ["models", "services", "templates", "scheduler"],
            "data_sync": ["models", "services", "sync", "config"],
            "webhook_handler": ["models", "api", "services", "handlers"],
            "scheduled_report": ["models", "services", "reports", "scheduler"],
            "database_backup": ["models", "services", "storage", "scheduler"],
            "api_monitor": ["models", "services", "monitor", "alerts"],
            "social_media_poster": ["models", "services", "channels", "scheduler"],
            "invoice_generator": ["models", "services", "templates", "pdf"],
            "notification_dispatcher": ["models", "services", "channels", "scheduler"],
        }
        return template_modules.get(template, ["models", "api", "services", "config"])

    def _default_entities(self, template: str) -> list:
        """Entidades por defecto según el template."""
        defaults = {
            "crm": [
                {"name": "Customer", "fields": ["id:int", "name:str", "email:str", "phone:str", "address:str", "created_at:datetime"]},
                {"name": "Sale", "fields": ["id:int", "customer_id:int", "amount:float", "date:datetime", "status:str"]},
            ],
            "inventory": [
                {"name": "Product", "fields": ["id:int", "name:str", "sku:str", "quantity:int", "price:float", "category:str"]},
                {"name": "Movement", "fields": ["id:int", "product_id:int", "type:str", "quantity:int", "date:datetime"]},
            ],
            "invoice_billing": [
                {"name": "Invoice", "fields": ["id:int", "customer_id:int", "items:list", "total:float", "date:datetime", "status:str"]},
                {"name": "Customer", "fields": ["id:int", "name:str", "email:str", "tax_id:str"]},
            ],
            "task_manager": [
                {"name": "Task", "fields": ["id:int", "title:str", "description:str", "status:str", "priority:str", "due_date:datetime"]},
                {"name": "Project", "fields": ["id:int", "name:str", "description:str", "status:str"]},
            ],
            "auth_system": [
                {"name": "User", "fields": ["id:int", "username:str", "email:str", "password_hash:str", "role:str", "active:bool"]},
            ],
            "web_api": [
                {"name": "Item", "fields": ["id:int", "name:str", "description:str", "data:dict", "created_at:datetime"]},
            ],
            "report_generator": [
                {"name": "Report", "fields": ["id:int", "name:str", "type:str", "data:dict", "generated_at:datetime"]},
            ],
            "scheduler": [
                {"name": "Appointment", "fields": ["id:int", "title:str", "date:datetime", "duration:int", "client:str", "status:str"]},
            ],
        }
        return defaults.get(template, [
            {"name": "Item", "fields": ["id:int", "name:str", "description:str", "created_at:datetime"]},
        ])

    def _generate_config(self, template: str, entities: list) -> dict:
        """Genera configuración por defecto para el proyecto."""
        return {
            "app_name": template.replace("_", " ").title(),
            "db_name": f"{template}.db",
            "port": 8000,
            "host": "0.0.0.0",
            "debug": True,
            "secret_key": os.environ.get("ZENIC_SECRET_KEY", "change-this-in-production"),
            "entity_count": len(entities),
        }

    def select_template(self, request: str):
        """Selecciona el mejor template para un request dado."""
        template = self._identify_template(request)
        confidence = 0.5
        if self._semantic and self._semantic.is_loaded:
            sim = self._semantic.similarity_text(request, template.replace("_", " "))
            confidence = max(confidence, sim)
        return template, confidence

    def customize_template(self, template_code: str, variables: dict,
                           request: str = "") -> str:
        """Personaliza un template con variables del contexto."""
        result = template_code
        for key, value in variables.items():
            placeholder = f"__{key.upper()}__"
            if placeholder in result:
                result = result.replace(placeholder, str(value))

        remaining_gaps = re.findall(r'__(\w+)__', result)
        if remaining_gaps and self._ai and self._ai.is_loaded:
            filled = self._ai.fill_template_gaps(result, variables)
            if filled and not re.search(r'__\w+__', filled):
                result = filled
            else:
                for gap in remaining_gaps:
                    result = result.replace(f"__{gap}__", self._gap_default(gap, variables))

        if request and self._ai and self._ai.is_loaded:
            enhanced = self._ai.generate_pattern(
                f"business logic for: {request[:100]}", "python"
            )
            if enhanced and len(enhanced) > 30:
                result = result.replace(
                    'return {"processed": True, "input": payload}',
                    '# Business logic (AI-generated)\n        return {"processed": True, "result": "customized", "input": payload}'
                )
        return result

    def _gap_default(self, gap: str, variables: dict) -> str:
        """Valor por defecto para un gap no rellenado."""
        gap_lower = gap.lower()
        defaults = {
            "APP_NAME": variables.get("app_name", "MyApp"),
            "DB_NAME": variables.get("db_name", "app.db"),
            "PORT": str(variables.get("port", 8000)),
            "HOST": variables.get("host", "0.0.0.0"),
            "SECRET_KEY": variables.get("secret_key", "change-this-in-production"),
            "ENTITY_NAME": variables.get("entity_name", "Item"),
            "ENTITY_NAME_LOWER": variables.get("entity_name", "Item").lower(),
            "FIELDS_INIT": "",
            "FIELDS_DICT": "{}",
            "TABLE_COLUMNS": "",
            "API_PREFIX": "/api",
        }
        return defaults.get(gap, gap.lower())
