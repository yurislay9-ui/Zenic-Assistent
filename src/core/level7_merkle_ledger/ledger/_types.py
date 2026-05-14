"""
ZENIC-AGENTS - Merkle Ledger v17 (Tenant-Aware + Sandbox Isolated)

Ledger con arbol Merkle real para integridad criptografica.
Soporta snapshots, commits con verificacion, y rollbacks atomicos.

v17 - TENANT-AWARE:
- Todas las operaciones filtran por tenant_id para aislar datos entre tenants
- Columna tenant_id con default '__anonymous__' para compatibilidad retroactiva
- purge_tenant_ledger() para GDPR / deprovisioning
- set_tenant_id() para cambio dinamico de contexto de tenant
- Thread-local TenantContext para obtener tenant_id automaticamente

v16 - AISLAMIENTO:
- Los commits se escriben en el workspace AISLADO del sandbox
- NUNCA escribe directamente en el filesystem del proyecto real
- Los snapshots y rollbacks operan dentro del workspace aislado
- Las DBs del ledger son INDEPENDIENTES cuando opera en sandbox

FIX (Phase 2): Added retry with exponential backoff for DB operations.
SQLite can fail transiently (database locked, busy timeout) especially
under concurrent write access.

Sin dependencias externas. Compatible con Android.
"""

import hashlib
import shutil
import sqlite3
import time
import logging
from pathlib import Path
from src.core.shared.contracts import MerkleNode
from src.core.shared.db_initializer import get_data_dir, get_connection
from src.core.shared.retry import with_retry
from src.core.shared.db_utils import purge_tenant_rows
from src.core.shared.tenant_utils import resolve_tenant_id


logger = logging.getLogger(__name__)

# Number of hex characters to use for hashed backup filenames
_BACKUP_HASH_LENGTH = 16


