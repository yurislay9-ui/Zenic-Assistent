"""MultiLanguage - Core methods."""

import logging
from typing import Any, Dict, List, Optional

from ._types import TYPE_MAP

logger = logging.getLogger("zenic_agents.multi_language")


class MultiLanguageCoreMixin:
    """Core methods mixin."""

    """Generate API projects in TypeScript, Go, and Kotlin."""

    def generate_project(self, entities: List[Dict], project_name: str,
                          language: str, description: str = "") -> Dict[str, str]:
        """Generate a complete API project in the target language.

        Args:
            entities: List of entity dicts with name + fields
            project_name: Name for the project
            language: "typescript", "go", or "kotlin"
            description: Project description

        Returns:
            Dict mapping filename → file content
        """
        if language == "typescript":
            return self._generate_typescript(entities, project_name, description)
        elif language == "go":
            return self._generate_go(entities, project_name, description)
        elif language == "kotlin":
            return self._generate_kotlin(entities, project_name, description)
        else:
            logger.warning(f"MultiLanguage: Unsupported language '{language}', falling back to TypeScript")
            return self._generate_typescript(entities, project_name, description)

    def _parse_fields(self, fields: list, language: str) -> List[Dict]:
        """Parse entity fields from YAML format.

        YAML fields are strings like "name:str", "price:decimal", "id:uuid"
        """
        parsed = []
        type_map = TYPE_MAP.get(language, TYPE_MAP["typescript"])

        for field_def in fields:
            if isinstance(field_def, str) and ":" in field_def:
                parts = field_def.split(":", 1)
                name = parts[0].strip()
                yaml_type = parts[1].strip().lower()
                target_type = type_map.get(yaml_type, "string" if language != "go" else "string")
                parsed.append({"name": name, "yaml_type": yaml_type, "type": target_type})
            elif isinstance(field_def, dict):
                name = field_def.get("name", "field")
                yaml_type = field_def.get("type", "str").lower()
                target_type = type_map.get(yaml_type, "string" if language != "go" else "string")
                parsed.append({"name": name, "yaml_type": yaml_type, "type": target_type})

        return parsed

    # ================================================================
    #  TYPESCRIPT (Express + TypeORM + Swagger)
    # ================================================================

    def _generate_typescript(self, entities: List[Dict], project_name: str,
                              description: str) -> Dict[str, str]:
        """Generate TypeScript Express project."""
        files = {}

        # package.json
        files["package.json"] = self._ts_package(project_name, description)

        # tsconfig.json
        files["tsconfig.json"] = self._ts_tsconfig()

        # Entity models
        for entity in entities:
            name = entity.get("name", "Item")
            fields = self._parse_fields(entity.get("fields", []), "typescript")
            files[f"src/models/{name.lower()}.model.ts"] = self._ts_model(name, fields)
            files[f"src/services/{name.lower()}.service.ts"] = self._ts_service(name, fields)
            files[f"src/routes/{name.lower()}.routes.ts"] = self._ts_routes(name)

        # Main app
        files["src/app.ts"] = self._ts_app(project_name, entities)

        # Database config
        files["src/config/database.ts"] = self._ts_database_config()

        # Docker
        files["Dockerfile"] = self._ts_dockerfile(project_name)

        return files

    def _ts_package(self, name: str, desc: str) -> str:
        return f'''{{
  "name": "{name}",
  "version": "1.0.0",
  "description": "{desc or name}",
  "main": "dist/app.js",
  "scripts": {{
    "build": "tsc",
    "start": "node dist/app.js",
    "dev": "ts-node-dev src/app.ts"
  }},
  "dependencies": {{
    "express": "^4.18.0",
    "typeorm": "^0.3.0",
    "better-sqlite3": "^9.0.0",
    "cors": "^2.8.5",
    "helmet": "^7.0.0",
    "swagger-ui-express": "^5.0.0",
    "class-validator": "^0.14.0",
    "class-transformer": "^0.5.0"
  }},
  "devDependencies": {{
    "typescript": "^5.3.0",
    "@types/express": "^4.17.0",
    "@types/cors": "^2.8.0",
    "ts-node-dev": "^2.0.0"
  }}
}}
'''

    def _ts_tsconfig(self) -> str:
        return '''{
  "compilerOptions": {
    "target": "ES2020",
    "module": "commonjs",
    "lib": ["ES2020"],
    "outDir": "./dist",
    "rootDir": "./src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist"]
}
'''

    def _ts_model(self, name: str, fields: List[Dict]) -> str:
        props = "\n".join(
            f"  {f['name']}: {f['type']};" for f in fields
        )
        return f'''import {{ Entity, PrimaryGeneratedColumn, Column }} from "typeorm";

@Entity("{name.lower()}s")
export class {name} {{
{props}
}}
'''

    def _ts_service(self, name: str, fields: List[Dict]) -> str:
        return f'''import {{ AppDataSource }} from "../config/database";
import {{ {name} }} from "../models/{name.lower()}.model";

export class {name}Service {{
  private repo = AppDataSource.getRepository({name});

  async create(data: Partial<{name}>): Promise<{name}> {{
    const item = this.repo.create(data);
    return await this.repo.save(item);
  }}

  async findById(id: number): Promise<{name} | null> {{
    return await this.repo.findOneBy({{ id }} as any);
  }}

  async findAll(limit: number = 50, offset: number = 0): Promise<{name}[]> {{
    return await this.repo.find({{ take: limit, skip: offset }});
  }}

  async update(id: number, data: Partial<{name}>): Promise<{name} | null> {{
    await this.repo.update(id, data as any);
    return await this.findById(id);
  }}

  async delete(id: number): Promise<boolean> {{
    const result = await this.repo.delete(id);
    return (result.affected ?? 0) > 0;
  }}
}}
'''

    def _ts_routes(self, name: str) -> str:
        return f'''import {{ Router, Request, Response }} from "express";
import {{ {name}Service }} from "../services/{name.lower()}.service";

const router = Router();
const service = new {name}Service();

router.post("/", async (req: Request, res: Response) => {{
  try {{
    const item = await service.create(req.body);
    res.status(201).json(item);
  }} catch (error) {{
    res.status(400).json({{ error: (error as Error).message }});
  }}
}});

router.get("/", async (req: Request, res: Response) => {{
  try {{
    const limit = parseInt(req.query.limit as string) || 50;
    const offset = parseInt(req.query.offset as string) || 0;
    const items = await service.findAll(limit, offset);
    res.json(items);
  }} catch (error) {{
    res.status(500).json({{ error: (error as Error).message }});
  }}
}});

router.get("/:id", async (req: Request, res: Response) => {{
  try {{
    const item = await service.findById(parseInt(req.params.id));
    if (!item) return res.status(404).json({{ error: "{name} not found" }});
    res.json(item);
  }} catch (error) {{
    res.status(500).json({{ error: (error as Error).message }});
  }}
}});

router.put("/:id", async (req: Request, res: Response) => {{
  try {{
    const item = await service.update(parseInt(req.params.id), req.body);
    if (!item) return res.status(404).json({{ error: "{name} not found" }});
    res.json(item);
  }} catch (error) {{
    res.status(400).json({{ error: (error as Error).message }});
  }}
}});

router.delete("/:id", async (req: Request, res: Response) => {{
  try {{
    const success = await service.delete(parseInt(req.params.id));
    if (!success) return res.status(404).json({{ error: "{name} not found" }});
    res.json({{ success: true }});
  }} catch (error) {{
    res.status(500).json({{ error: (error as Error).message }});
  }}
}});

export default router;
'''

    def _ts_app(self, project_name: str, entities: List[Dict]) -> str:
        imports = [f'import {e["name"].lower()}Routes from "./routes/{e["name"].lower()}.routes";'
                   for e in entities]
        uses = [f'app.use("/v1/{e["name"].lower()}s", {e["name"].lower()}Routes);'
                for e in entities]
        return f'''import express from "express";
import cors from "cors";
import helmet from "helmet";
import {{ AppDataSource }} from "./config/database";
{chr(10).join(imports)}

const app = express();
const PORT = process.env.PORT || 3000;

app.use(helmet());
app.use(cors());
app.use(express.json());

{chr(10).join(uses)}

app.get("/health", (req, res) => {{
  res.json({{ status: "ok", service: "{project_name}" }});
}});

AppDataSource.initialize()
  .then(() => {{
    app.listen(PORT, () => {{
      console.log(`{project_name} running on port ${{PORT}}`);
    }});
  }})
  .catch((error) => {{
    console.error("Database connection failed:", error);
    process.exit(1);
  }});

export default app;
'''

    def _ts_database_config(self) -> str:
        return '''import { DataSource } from "typeorm";

export const AppDataSource = new DataSource({
  type: "better-sqlite3",
  database: process.env.DB_PATH || "data.sqlite",
  synchronize: true,
  logging: false,
  entities: ["src/models/**/*.model.ts"],
});
'''

    def _ts_dockerfile(self, name: str) -> str:
        return f'''FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY dist ./dist
EXPOSE 3000
CMD ["node", "dist/app.js"]
'''

    # ================================================================
    #  GO (Gin + GORM + Swagger)
    # ================================================================

