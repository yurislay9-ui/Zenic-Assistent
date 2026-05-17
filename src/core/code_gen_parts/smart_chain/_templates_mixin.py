"""SmartPromptChain - Template Fallbacks Mixin."""

import re
import logging
from typing import Any, Dict, List, Optional

from ._types import GenerationStep

logger = logging.getLogger("zenic_agents.code_gen_parts.smart_chain")


class SmartChainTemplatesMixin:
    """Mixin providing template-based fallback code generation."""

    def _fallback_imports(self, desc: str) -> str:
        """Generate REAL import statements based on task type."""
        desc_lower = desc.lower()

        if "auth" in desc_lower or "jwt" in desc_lower:
            return (
                "import hashlib\nimport secrets\nimport hmac\nimport os\n"
                "import time\nimport logging\nfrom typing import Optional, Dict, Any, List\n"
                "from datetime import datetime, timedelta\n\n"
                "try:\n    from jose import JWTError, jwt\n    JOSE_AVAILABLE = True\n"
                "except ImportError:\n    JOSE_AVAILABLE = False\n\n"
                "try:\n    from passlib.context import CryptContext\n    PASSLIB_AVAILABLE = True\n"
                "except ImportError:\n    PASSLIB_AVAILABLE = False\n\n"
                "logger = logging.getLogger(__name__)\n"
            )
        elif "crud" in desc_lower or "service" in desc_lower:
            return (
                "import sqlite3\nimport logging\nimport re\nimport json\n"
                "from typing import Optional, Dict, Any, List, Tuple\n"
                "from contextlib import contextmanager\n\n"
                "logger = logging.getLogger(__name__)\n\n\n"
                "def get_connection(db_path: str = 'data.sqlite'):\n"
                "    \"\"\"Get SQLite connection with WAL mode.\"\"\"\n"
                "    conn = sqlite3.connect(db_path)\n"
                "    conn.row_factory = sqlite3.Row\n"
                "    conn.execute('PRAGMA journal_mode=WAL')\n"
                "    return conn\n"
            )
        elif "analytics" in desc_lower:
            return (
                "import sqlite3\nimport logging\nfrom typing import Optional, Dict, Any, List\n"
                "from datetime import datetime, timedelta\nfrom collections import Counter\n\n"
                "logger = logging.getLogger(__name__)\n"
            )
        elif "integration" in desc_lower or "stripe" in desc_lower or "payment" in desc_lower:
            return (
                "import asyncio\nimport logging\nimport json\nimport os\n"
                "from typing import Optional, Dict, Any, List\n\n"
                "try:\n    import aiohttp\n    AIOHTTP_AVAILABLE = True\n"
                "except ImportError:\n    AIOHTTP_AVAILABLE = False\n\n"
                "try:\n    import urllib.request\n    URLLIB_AVAILABLE = True\n"
                "except ImportError:\n    URLLIB_AVAILABLE = False\n\n"
                "logger = logging.getLogger(__name__)\n"
            )
        else:
            return (
                "import logging\nfrom typing import Optional, Dict, Any, List\n\n"
                "logger = logging.getLogger(__name__)\n"
            )

    def _fallback_schema(self, desc: str) -> str:
        """Generate REAL Pydantic models based on task type."""
        desc_lower = desc.lower()

        if "auth" in desc_lower:
            return (
                "\n\n"
                "class UserCreate:\n"
                "    \"\"\"Schema for user registration.\"\"\"\n"
                "    def __init__(self, username: str, email: str, password: str, role: str = 'user'):\n"
                "        self.username = username\n"
                "        self.email = email\n"
                "        self.password = password\n"
                "        self.role = role\n\n"
                "class UserResponse:\n"
                "    \"\"\"Schema for user response.\"\"\"\n"
                "    def __init__(self, id: int, username: str, email: str, role: str, created_at: str):\n"
                "        self.id = id\n"
                "        self.username = username\n"
                "        self.email = email\n"
                "        self.role = role\n"
                "        self.created_at = created_at\n\n"
                "class TokenResponse:\n"
                "    \"\"\"Schema for token response.\"\"\"\n"
                "    def __init__(self, access_token: str, token_type: str = 'bearer', expires_in: int = 1800):\n"
                "        self.access_token = access_token\n"
                "        self.token_type = token_type\n"
                "        self.expires_in = expires_in\n"
            )

        # Extract entity name from description
        entity_name = "Item"
        for word in desc.split():
            if word[0].isupper() and len(word) > 2:
                entity_name = word
                break

        return (
            f"\n\n"
            f"class {entity_name}Create:\n"
            f"    \"\"\"Schema for creating a {entity_name}.\"\"\"\n"
            f"    def __init__(self, name: str, status: str = 'active', **kwargs):\n"
            f"        self.name = name\n"
            f"        self.status = status\n"
            f"        for key, value in kwargs.items():\n"
            f"            setattr(self, key, value)\n\n"
            f"class {entity_name}Response:\n"
            f"    \"\"\"Schema for {entity_name} response.\"\"\"\n"
            f"    def __init__(self, id: int, name: str, status: str, created_at: str):\n"
            f"        self.id = id\n"
            f"        self.name = name\n"
            f"        self.status = status\n"
            f"        self.created_at = created_at\n"
        )

    def _fallback_class_def(self, desc: str) -> str:
        """Generate REAL class definition with __init__ based on task type."""
        desc_lower = desc.lower()

        # Extract class name from description
        class_name = "ModuleService"
        match = re.search(r'(\w+?)(?:Service|Client|Manager|CRUD)', desc)
        if match:
            class_name = match.group(1) + "Service"
        else:
            for word in desc.split():
                if word[0].isupper() and len(word) > 2:
                    class_name = word + "Service"
                    break

        table_name = class_name.lower().replace("service", "s")

        if "auth" in desc_lower:
            return (
                f"\n\nclass AuthService:\n"
                f'    \"\"\"Authentication service with JWT and password hashing.\"\"\"\n\n'
                f"    def __init__(self, secret_key: str = None, token_expire_minutes: int = 30):\n"
                f"        self._secret_key = secret_key or secrets.token_hex(32)\n"
                f"        self._token_expire = token_expire_minutes\n"
                f"        self._db_path = 'auth.sqlite'\n"
                f"        self._init_db()\n\n"
                f"    def _init_db(self):\n"
                f'        \"\"\"Initialize users table.\"\"\"\n'
                f"        conn = get_connection(self._db_path)\n"
                f"        conn.execute('''\n"
                f"            CREATE TABLE IF NOT EXISTS users (\n"
                f"                id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
                f"                username TEXT UNIQUE NOT NULL,\n"
                f"                email TEXT UNIQUE NOT NULL,\n"
                f"                password_hash TEXT NOT NULL,\n"
                f"                role TEXT DEFAULT 'user',\n"
                f"                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n"
                f"            )\n"
                f"        ''')\n"
                f"        conn.commit()\n"
                f"        conn.close()\n"
            )

        if "integration" in desc_lower or "stripe" in desc_lower:
            return (
                f"\n\nclass {class_name}:\n"
                f'    \"\"\"Integration client with retry and error handling.\"\"\"\n\n'
                f"    def __init__(self, api_key: str = None, base_url: str = ''):\n"
                f"        self._api_key = api_key or os.getenv('API_KEY', '')\n"
                f"        self._base_url = base_url\n"
                f"        self._headers = {{'Authorization': f'Bearer {{self._api_key}}', 'Content-Type': 'application/json'}}\n"
                f"        self._max_retries = 3\n"
                f"        self._timeout = 30\n"
            )

        # SECURITY: Validate table_name at generation time
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table_name):
            raise ValueError(f"Invalid table name for code generation: {table_name!r}")

        # Default: CRUD service with real database
        return (
            f"\n\nclass {class_name}:\n"
            f'    \"\"\"CRUD service for {table_name} with real SQLite operations.\"\"\"\n\n'
            f"    _SAFE_ID = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')\n\n"
            f"    def __init__(self, db_path: str = 'data.sqlite', table_name: str = '{table_name}'):\n"
            f"        # SECURITY: Validate table_name to prevent SQL injection\n"
            f"        if not self._SAFE_ID.match(table_name):\n"
            f"            raise ValueError(f'Invalid table name: {{table_name!r}}')\n"
            f"        self._db_path = db_path\n"
            f"        self._table_name = table_name\n"
            f"        self._init_db()\n\n"
            f"    def _init_db(self):\n"
            f'        \"\"\"Initialize table with schema.\"\"\"\n'
            f"        conn = get_connection(self._db_path)\n"
            f"        conn.execute(f'''CREATE TABLE IF NOT EXISTS {{self._table_name}} (\n"
            f"            id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
            f"            name TEXT NOT NULL,\n"
            f"            status TEXT DEFAULT 'active',\n"
            f"            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n"
            f"        )''')\n"
            f"        conn.commit()\n"
            f"        conn.close()\n"
        )

    def _fallback_method(self, desc: str) -> str:
        """Generate REAL method code based on task type."""
        desc_lower = desc.lower()

        if "hash_password" in desc_lower or "verify_password" in desc_lower:
            return (
                "\n"
                "    def hash_password(self, password: str) -> str:\n"
                '        """Hash password using PBKDF2 with random salt."""\n'
                "        salt = secrets.token_hex(16)\n"
                "        dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)\n"
                '        return f"{salt}:{dk.hex()}"\n\n'
                "    def verify_password(self, password: str, stored_hash: str) -> bool:\n"
                '        """Verify password against stored hash."""\n'
                "        try:\n"
                '            salt, hash_val = stored_hash.split(":")\n'
                "            dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)\n"
                "            return hmac.compare_digest(dk.hex(), hash_val)\n"
                "        except (ValueError, AttributeError):\n"
                "            return False\n"
            )

        if "create_token" in desc_lower or "verify_token" in desc_lower:
            return (
                "\n"
                "    def create_token(self, user_id: int, role: str = 'user') -> str:\n"
                '        """Create JWT token for user."""\n'
                "        if JOSE_AVAILABLE:\n"
                "            payload = {'sub': user_id, 'role': role, 'exp': datetime.utcnow() + timedelta(minutes=self._token_expire)}\n"
                "            return jwt.encode(payload, self._secret_key, algorithm='HS256')\n"
                "        else:\n"
                "            # Fallback: HMAC-based token\n"
                "            payload = f'{user_id}:{role}:{int(time.time()) + self._token_expire * 60}'\n"
                "            sig = hmac.new(self._secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()\n"
                '            return f"{payload}:{sig}"\n\n'
                "    def verify_token(self, token: str) -> Optional[Dict]:\n"
                '        """Verify and decode JWT token."""\n'
                "        try:\n"
                "            if JOSE_AVAILABLE:\n"
                "                payload = jwt.decode(token, self._secret_key, algorithms=['HS256'])\n"
                "                return {'user_id': payload['sub'], 'role': payload['role']}\n"
                "            else:\n"
                "                parts = token.split(':')\n"
                "                if len(parts) == 3:\n"
                "                    user_id, role, exp = parts[0], parts[1], int(parts[2])\n"
                "                    if time.time() < exp:\n"
                "                        return {'user_id': int(user_id), 'role': role}\n"
                "        except Exception:\n"
                "            pass\n"
                "        return None\n"
            )

        if "create" in desc_lower:
            # Extract entity from description
            entity = "item"
            for word in desc.split():
                if word[0].isupper() and word not in ("The", "Create", "Generate", "A", "An"):
                    entity = word.lower()
                    break
            return (
                f"\n"
                f"    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:\n"
                f'        \"\"\"Create a new {entity} with parameterized SQL INSERT.\"\"\"\n'
                f"        try:\n"
                f"            conn = get_connection(self._db_path)\n"
                f"            columns = list(data.keys())\n"
            f"            # SECURITY: Validate column names before SQL interpolation\n"
            f"            for col in columns:\n"
            f"                if not self._SAFE_ID.match(str(col)):\n"
            f"                    return {{'success': False, 'error': f'Invalid column: {{col!r}}'}}\n"
                f"            values = list(data.values())\n"
                f"            placeholders = ', '.join(['?' for _ in columns])\n"
                f"            col_str = ', '.join(columns)\n"
                f"            cursor = conn.execute(\n"
                f"                f'INSERT INTO {{self._table_name}} ({{col_str}}) VALUES ({{placeholders}})',\n"
                f"                values\n"
                f"            )\n"
                f"            conn.commit()\n"
                f"            new_id = cursor.lastrowid\n"
                f"            conn.close()\n"
                f"            return {{'success': True, 'id': new_id, 'data': data}}\n"
                f"        except Exception as e:\n"
                f"            logger.error(f'Create failed: {{e}}')\n"
                f"            return {{'success': False, 'error': str(e)}}\n"
            )

        if "read" in desc_lower or "list" in desc_lower:
            return (
                "\n"
                "    def read(self, item_id: int) -> Optional[Dict]:\n"
                '        """Read a single item by ID."""\n'
                "        try:\n"
                "            conn = get_connection(self._db_path)\n"
                "            # SECURITY: self._table_name validated in __init__\n"
                "            row = conn.execute(f'SELECT * FROM {self._table_name} WHERE id = ?', (item_id,)).fetchone()\n"
                "            conn.close()\n"
                "            return dict(row) if row else None\n"
                "        except Exception as e:\n"
                "            logger.error(f'Read failed: {e}')\n"
                "            return None\n\n"
                "    def list(self, limit: int = 50, offset: int = 0, status: str = None) -> List[Dict]:\n"
                '        """List items with optional filtering."""\n'
                "        try:\n"
                "            conn = get_connection(self._db_path)\n"
                "            if status:\n"
                "                rows = conn.execute(f'SELECT * FROM {self._table_name} WHERE status = ? LIMIT ? OFFSET ?', (status, limit, offset)).fetchall()\n"
                "            else:\n"
                "                rows = conn.execute(f'SELECT * FROM {self._table_name} LIMIT ? OFFSET ?', (limit, offset)).fetchall()\n"
                "            conn.close()\n"
                "            return [dict(r) for r in rows]\n"
                "        except Exception as e:\n"
                "            logger.error(f'List failed: {e}')\n"
                "            return []\n"
            )

        if "update" in desc_lower or "delete" in desc_lower:
            return (
                "\n"
                "    def update(self, item_id: int, data: Dict[str, Any]) -> Dict[str, Any]:\n"
                '        """Update an item by ID with parameterized SQL."""\n'
                "        try:\n"
                "            conn = get_connection(self._db_path)\n"
                "            # SECURITY: Validate column names before SQL interpolation\n"
                "            for k in data.keys():\n"
                "                if not self._SAFE_ID.match(str(k)):\n"
                "                    return {'success': False, 'error': f'Invalid column: {k!r}'}\n"
                "            set_parts = [f'{k} = ?' for k in data.keys()]\n"
                "            values = list(data.values()) + [item_id]\n"
                "            conn.execute(f'UPDATE {self._table_name} SET {\", \".join(set_parts)} WHERE id = ?', values)\n"
                "            conn.commit()\n"
                "            conn.close()\n"
                "            return {'success': True, 'id': item_id, 'updated_fields': list(data.keys())}\n"
                "        except Exception as e:\n"
                "            logger.error(f'Update failed: {e}')\n"
                "            return {'success': False, 'error': str(e)}\n\n"
                "    def delete(self, item_id: int) -> Dict[str, Any]:\n"
                '        """Delete an item by ID."""\n'
                "        try:\n"
                "            conn = get_connection(self._db_path)\n"
                "            # SECURITY: self._table_name validated in __init__\n"
                "            conn.execute(f'DELETE FROM {self._table_name} WHERE id = ?', (item_id,))\n"
                "            conn.commit()\n"
                "            conn.close()\n"
                "            return {'success': True, 'id': item_id}\n"
                "        except Exception as e:\n"
                "            logger.error(f'Delete failed: {e}')\n"
                "            return {'success': False, 'error': str(e)}\n"
            )

        if "aggregate" in desc_lower or "summary" in desc_lower or "analytics" in desc_lower:
            return (
                "\n"
                "    def get_summary(self) -> Dict[str, Any]:\n"
                '        """Get aggregate summary statistics."""\n'
                "        try:\n"
                "            conn = get_connection(self._db_path)\n"
                "            # SECURITY: self._table_name validated in __init__\n"
                "            total = conn.execute(f'SELECT COUNT(*) FROM {self._table_name}').fetchone()[0]\n"
                "            by_status = conn.execute(f'SELECT status, COUNT(*) as cnt FROM {self._table_name} GROUP BY status').fetchall()\n"
                "            conn.close()\n"
                "            return {'total': total, 'by_status': [dict(r) for r in by_status]}\n"
                "        except Exception as e:\n"
                "            logger.error(f'Summary failed: {e}')\n"
                "            return {'total': 0, 'error': str(e)}\n\n"
                "    def get_trends(self, metric: str = 'count', period: str = 'daily', days: int = 30) -> List[Dict]:\n"
                '        """Get trend data over time."""\n'
                "        try:\n"
                "            conn = get_connection(self._db_path)\n"
                "            # SECURITY: Validate metric name before SQL interpolation\n"
                "            if not self._SAFE_ID.match(str(metric)):\n"
                "                return []\n"
                "            days = int(days)  # Ensure integer to prevent injection\n"
                "            rows = conn.execute(\n"
                "                f\"SELECT date(created_at) as period, COUNT(*) as {metric} FROM {self._table_name} \"\n"
                "                f\"WHERE created_at >= datetime('now', '-' || ? || ' days') \"\n"
                "                f\"GROUP BY period ORDER BY period\", (days,)\n"
                "            ).fetchall()\n"
                "            conn.close()\n"
                "            return [dict(r) for r in rows]\n"
                "        except Exception as e:\n"
                "            logger.error(f'Trends failed: {e}')\n"
                "            return []\n"
            )

        # Generic execute method with real CRUD
        return (
            "\n"
            "    def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:\n"
            '        """Execute operation based on action type."""\n'
            "        action = payload.get('action', 'list')\n\n"
            "        if action == 'create':\n"
            "            return self.create(payload.get('data', {}))\n"
            "        elif action == 'read':\n"
            "            result = self.read(payload.get('id'))\n"
            "            return {'success': bool(result), 'data': result}\n"
            "        elif action == 'update':\n"
            "            return self.update(payload.get('id'), payload.get('data', {}))\n"
            "        elif action == 'delete':\n"
            "            return self.delete(payload.get('id'))\n"
            "        elif action == 'list':\n"
            "            items = self.list(payload.get('limit', 50), payload.get('offset', 0))\n"
            "            return {'success': True, 'data': items, 'count': len(items)}\n"
            "        elif action == 'search':\n"
            "            items = self.search(payload.get('query', ''), payload.get('column', 'name'))\n"
            "            return {'success': True, 'data': items, 'count': len(items)}\n"
            "        else:\n"
            "            return {'success': False, 'error': f'Unknown action: {action}'}\n"
        )

