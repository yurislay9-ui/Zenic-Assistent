"""
ZENIC-AGENTS - Theorem Cache v17 (Tenant-Aware + Skeleton Hash + LRU Eviction)

Cache de teoremas con destilacion topologica (skeleton hash).
Normaliza AST, elimina nombres de variables, y guarda esqueletos
estructurales para bypass O(1) en mutaciones repetidas.

v17 - TENANT-AWARE:
- Todas las operaciones filtran por tenant_id para aislar datos entre tenants
- Columna tenant_id con default '__anonymous__' para compatibilidad retroactiva
- PRIMARY KEY ahora es (structural_hash, tenant_id) para permitir el mismo
  hash en diferentes tenants
- purge_tenant_cache() para GDPR / deprovisioning
- set_tenant_id() para cambio dinamico de contexto de tenant
- Eviction solo afecta entradas del tenant actual
- get_stats() scoped por tenant_id
- Thread-local TenantContext para obtener tenant_id automaticamente

v16 EVICTION: Politica LRU con limite de entradas y limpieza automatica.
Previene que la cache crezca sin control en dispositivos ARM con RAM limitada.

FIX (Phase 2): Added retry with exponential backoff for DB operations.
SQLite can fail transiently (database locked, busy timeout).

Sin dependencias externas. Compatible con Android.
"""

import ast
import re
import hashlib
import json
import time
import logging
from typing import Any, Dict, Optional
from src.core.shared.contracts import IntentPayload
from src.core.shared.db_initializer import get_connection
from src.core.shared.retry import with_retry
from src.core.shared.db_utils import purge_tenant_rows
from src.core.shared.tenant_utils import resolve_tenant_id

logger = logging.getLogger(__name__)

# Named constants (previously magic numbers)
_DEFAULT_MAX_ENTRIES = 500
_CODE_HASH_LENGTH = 16
_EVICTION_THRESHOLD = 0.9
_EVICTION_HIT_PROTECTION = 50

__all__ = ["TheoremCache"]


class TheoremCache:
    """
    Cache con destilacion topologica + politica de eviction LRU. Tenant-aware.

    Implementa el Nivel 8 del documento de arquitectura:
    - Hash compuesto (operacion + objetivo + target) para lookup directo
    - Skeleton hash (topologia AST pura sin nombres) para bypass estructural
    - Hit counter para metricas de eficiencia
    - LRU eviction: elimina entradas menos usadas cuando se alcanza el limite
    - Max entries configurable para ARM (default: 500)
    - Auto-eviction en cada save si el limite se supera
    - Tenant-aware: todas las operaciones scoped por tenant_id
    """

    def __init__(self, max_entries: int = _DEFAULT_MAX_ENTRIES):
        """
        Inicializa el cache con politica de eviction.

        Args:
            max_entries: Maximo numero de entradas en cache (default 500).
                        En ARM con 12GB RAM, 500 entries ~ 5MB es seguro.
        """
        self.max_entries = max_entries
        self._tenant_id: str = resolve_tenant_id()
        logger.debug("TheoremCache initialized with tenant_id='%s'", self._tenant_id)

    def set_tenant_id(self, tenant_id: str) -> None:
        """Update the current tenant_id for this cache instance.

        Args:
            tenant_id: New tenant identifier to scope all operations.
        """
        old = self._tenant_id
        self._tenant_id = tenant_id
        logger.info("TheoremCache tenant_id changed: '%s' -> '%s'", old, tenant_id)

    def _skeleton_hash(self, code, language="python"):
        """
        Genera un hash de la topologia sintactica pura del codigo.

        Elimina todos los rasgos humanos (nombres de variables, strings)
        y guarda solo el "esqueleto" estructural.

        Ejemplo: Una funcion con 3 args, 2 ifs y 1 return
        genera: "FN(3,2,1)" -> hash SHA256
        """
        if language == "python":
            try:
                tree = ast.parse(code)
                skeleton_parts = []
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        num_args = len(node.args.args)
                        complexity = sum(1 for n in ast.walk(node)
                                       if isinstance(n, (ast.If, ast.While, ast.For, ast.ExceptHandler)))
                        num_returns = sum(1 for n in ast.walk(node) if isinstance(n, ast.Return))
                        skeleton_parts.append(f"FN({num_args},{complexity},{num_returns})")
                    elif isinstance(node, ast.ClassDef):
                        num_methods = sum(1 for n in node.body
                                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
                        skeleton_parts.append(f"CLS({num_methods})")
                    elif isinstance(node, ast.Import):
                        skeleton_parts.append("IMP")
                    elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp)):
                        skeleton_parts.append("COMP")
                skeleton = "|".join(skeleton_parts)
                return hashlib.sha256(skeleton.encode()).hexdigest()
            except SyntaxError:
                pass

        # Fallback para otros lenguajes: normalizar por regex
        structure = re.sub(r'\b(?!def|class|return|if|for|while|try|with|import|from|else|elif|pass|raise|except|async|await|yield|break|continue|lambda|not|and|or|is|in|True|False|None)\w+\b', 'X', code)
        structure = re.sub(r'".*?"', '"S"', structure)
        structure = re.sub(r"'.*?'", "'S'", structure)
        structure = re.sub(r'#.*', '', structure)
        return hashlib.sha256(structure.encode()).hexdigest()

    def _hash(self, intent, code=None):
        """Compute composite hash from operation, goal, target, and optional code.

        Args:
            intent: IntentPayload with op, goal, and target attributes.
            code: Optional source code string to include in the hash.

        Returns:
            Hex-encoded SHA-256 digest string.
        """
        composite = f"{intent.op}|{intent.goal}|{intent.target}"
        if code:
            code_hash = hashlib.sha256(code.encode()).hexdigest()[:_CODE_HASH_LENGTH]
            composite = f"{composite}|{code_hash}"
        return hashlib.sha256(composite.encode()).hexdigest()

    def lookup(self, intent, code=None, language="python") -> 'Optional[Dict[str, Any]]':
        """
        Busca en la cache usando hash compuesto primero,
        luego skeleton hash como fallback estructural.

        Todas las busquedas se filtran por tenant_id para
        prevenir cross-tenant data leakage.
        """
        tid = self._tenant_id
        try:
            conn = get_connection("theorem_cache.sqlite")
            # Busqueda directa por hash compuesto + tenant_id
            intent_hash = self._hash(intent, code)
            r = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT solution_payload, hit_count FROM theorems WHERE structural_hash=? AND tenant_id=?",
                (intent_hash, tid)).fetchone()
            if r:
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "UPDATE theorems SET hit_count=hit_count+1, last_used=CURRENT_TIMESTAMP WHERE structural_hash=? AND tenant_id=?",
                    (intent_hash, tid))
                conn.commit()
                return {"source": "composite_hash", "data": json.loads(r[0]), "hits": r[1]}

            # Busqueda por skeleton hash (bypass experiencial) + tenant_id
            if code:
                sk_hash = self._skeleton_hash(code, language)
                r = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "SELECT solution_payload, hit_count FROM theorems WHERE skeleton_hash=? AND tenant_id=?",
                    (sk_hash, tid)).fetchone()
                if r:
                    conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "UPDATE theorems SET hit_count=hit_count+1, last_used=CURRENT_TIMESTAMP WHERE skeleton_hash=? AND tenant_id=?",
                        (sk_hash, tid))
                    conn.commit()
                    return {"source": "skeleton_hash", "data": json.loads(r[0]), "hits": r[1]}
        except Exception as e:
            logger.debug("Cache lookup error: %s", e)
        return None

    def save(self, intent, proof, sol, code=None, language="python") -> None:
        """Save a proof with composite and skeleton hash. Runs LRU eviction.

        Uses shared retry utility for transient SQLite failures.
        """
        tid = self._tenant_id

        def _save_entry():
            skeleton_hash = None
            if code:
                skeleton_hash = self._skeleton_hash(code, language)
            conn = get_connection("theorem_cache.sqlite")
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """INSERT INTO theorems
                (structural_hash, operation, goal, proof_result, solution_payload, skeleton_hash, tenant_id)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(structural_hash, tenant_id) DO UPDATE SET
                    proof_result=excluded.proof_result,
                    solution_payload=excluded.solution_payload,
                    skeleton_hash=excluded.skeleton_hash""",
                (self._hash(intent, code), intent.op, intent.goal, proof,
                 json.dumps(sol), skeleton_hash, tid))
            conn.commit()
            # Eviction: remove LRU entries if limit exceeded (scoped by tenant)
            self._evict_if_needed(conn)

        try:
            with_retry(_save_entry, label="TheoremCache save")
        except Exception:
            pass  # with_retry already logged the failure

    def _evict_if_needed(self, conn):
        """
        Eviction LRU: elimina las entradas menos recientemente usadas
        cuando el cache supera el limite de entradas.

        SOLO se consideran y eliminan entradas del tenant actual,
        previniendo que un tenant afecte el cache de otro.

        Estrategia:
        1. Contar entradas actuales del tenant
        2. Si count > max_entries, eliminar las (count - max_entries) mas viejas
        3. Priorizar eliminacion de entradas con bajo hit_count
        4. Nunca eliminar entradas con hit_count > 50 (altamente valiosas)
        """
        tid = self._tenant_id
        try:
            # Only count entries for the current tenant
            count = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT COUNT(*) FROM theorems WHERE tenant_id=?", (tid,)
            ).fetchone()[0]

            if count <= self.max_entries:
                return

            # Calcular cuantas entradas eliminar (10% extra para evitar eviction frecuente)
            to_evict = count - int(self.max_entries * _EVICTION_THRESHOLD)

            if to_evict <= 0:
                return

            # LRU eviction: eliminar las mas viejas con menor hit_count
            # Proteger entradas altamente usadas (hit_count > 50)
            # ONLY evict within the current tenant's scope
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """DELETE FROM theorems
                WHERE rowid IN (
                    SELECT rowid FROM theorems
                    WHERE tenant_id=? AND hit_count <= _EVICTION_HIT_PROTECTION
                    ORDER BY last_used ASC, hit_count ASC
                    LIMIT ?
                )""",
                (tid, to_evict)
            )
            conn.commit()

            # Actualizar stats
            remaining = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT COUNT(*) FROM theorems WHERE tenant_id=?", (tid,)
            ).fetchone()[0]
            logger.info(
                "Cache eviction [tenant=%s]: removed %d entries, %d remaining (max: %d)",
                tid, to_evict, remaining, self.max_entries
            )
        except Exception as e:
            logger.debug("Cache eviction error: %s", e)

    def get_stats(self) -> Dict[str, Any]:
        """Return cache statistics scoped by the current tenant.

        Returns:
            Dict with keys: tenant_id, entries, max_entries, usage_pct,
            total_hits, avg_hits, max_hits.
        """
        tid = self._tenant_id
        try:
            conn = get_connection("theorem_cache.sqlite")
            count = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT COUNT(*) FROM theorems WHERE tenant_id=?", (tid,)
            ).fetchone()[0]
            total_hits = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT COALESCE(SUM(hit_count), 0) FROM theorems WHERE tenant_id=?", (tid,)
            ).fetchone()[0]
            avg_hits = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT COALESCE(AVG(hit_count), 0) FROM theorems WHERE tenant_id=?", (tid,)
            ).fetchone()[0]
            max_hits_row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT hit_count FROM theorems WHERE tenant_id=? ORDER BY hit_count DESC LIMIT 1",
                (tid,)
            ).fetchone()
            max_hits = max_hits_row[0] if max_hits_row else 0
            return {
                "tenant_id": tid,
                "entries": count,
                "max_entries": self.max_entries,
                "usage_pct": round(count / self.max_entries * 100, 1) if self.max_entries > 0 else 0,
                "total_hits": total_hits,
                "avg_hits": round(avg_hits, 1),
                "max_hits": max_hits,
            }
        except Exception:
            return {"tenant_id": tid, "entries": 0, "max_entries": self.max_entries, "usage_pct": 0}

    def clear(self):
        """Clear all cache entries for the current tenant."""
        tid = self._tenant_id
        try:
            conn = get_connection("theorem_cache.sqlite")
            conn.execute("DELETE FROM theorems WHERE tenant_id=?", (tid,))  # nosemgrep: sqlalchemy-execute-raw-query
            conn.commit()
            logger.info("Cache cleared for tenant '%s'", tid)
        except Exception as e:
            logger.warning("Cache clear error: %s", e)

    def purge_tenant_cache(self, tenant_id: str) -> int:
        """Delete all cache entries for a specific tenant (GDPR / deprovisioning)."""
        try:
            conn = get_connection("theorem_cache.sqlite")
            return purge_tenant_rows(conn, "theorems", tenant_id)
        except Exception as e:
            logger.error("TheoremCache: purge failed for tenant '%s': %s", tenant_id, e)
            return 0
