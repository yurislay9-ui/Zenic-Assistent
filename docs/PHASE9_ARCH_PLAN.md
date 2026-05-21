# FASE 9: PLAN DE REMEDIACIÓN ARQUITECTÓNICA
## Zenic-Agents v3.0.0 — Hallazgos H-78 a H-99

---

## 1. RESUMEN EJECUTIVO

| Métrica | Valor |
|---------|-------|
| Total hallazgos | 22 |
| 🔴 Críticos | 3 (H-78, H-79, H-80) |
| 🟠 Altos | 7 (H-81 a H-87) |
| 🟡 Medios | 9 (H-88 a H-96) |
| 🟢 Bajos | 3 (H-97, H-98, H-99) |
| Archivos impactados | ~25 |
| Fases de ejecución | 7 |
| Riesgo de breaking change | 4 hallazgos |

---

## 2. MATRIZ DE RIESGO DETALLADA

### 🔴 CRÍTICOS (Impacto existencial o violación de invariantes fundamentales)

| ID | Hallazgo | CVSS | Componente | Riesgo |
|----|----------|------|------------|--------|
| H-78 | Multi-tenant deshabilitado | 9.1 | `tenant_utils.py` | Todos los datos comparten namespace `__anonymous__` — sin aislamiento entre clientes |
| H-79 | HMAC fallback forja ECDSA | 8.7 | `signer.py` | Atacante con HMAC key puede firmar licencias que el verificador acepta como ECDSA |
| H-80 | SafetyGate DENY override | 8.3 | `_gate.py` + pybridge | `_denied_actions` se resetea con `reset_safety_gate()` — pérd. de invariantes DENY |

### 🟠 ALTOS (Degradación de seguridad o pérdida de garantías)

| ID | Hallazgo | CVSS | Componente | Riesgo |
|----|----------|------|------------|--------|
| H-81 | Merkle ledger sin protección | 7.8 | `_merkle.py` + `merkle-audit.ts` | Cadena en memoria sin persistencia — reinicio = pérdida de integridad |
| H-82 | 10+ módulos Rust sin fallback Python | 7.5 | `zenic-pybridge/` | Si `_zenic_native` falla al cargar, 20+ capacidades desaparecen silenciosamente |
| H-83 | God Object orchestrator | 7.2 | `orchestrator.py` + `orchestrator_base.py` | 8 fases de init, 30+ dependencias — cambio en 1 área rompe 5 |
| H-84 | Versiones duplicadas _zenic_native | 7.0 | `classify.rs` vs `gate.rs`, `crypto.rs` vs `merkle_seal.rs` | Lógica divergente — `niche_onboarding` solo en Rust, no en pybridge |
| H-85 | Encriptación degrada a plaintext | 7.4 | `encryption.py` L247-248 | `encrypt()` retorna plaintext si Fernet no disponible — falso sentido de seguridad |
| H-86 | Salt Fernet estático (residual) | 6.8 | `merkle_seal.rs` | FIX SEC-6 ya aplicado en Python. **RESIDUAL:** `update_root()` inconsistente con `compute()` en Rust |
| H-87 | SQLCipher KDF demasiado bajo | 6.5 | `encryption.py` L72 | PBKDF2 100K iteraciones — OWASP 2024 recomienda 600K para SHA-256 |

### 🟡 MEDIOS (Problemas operativos o de diseño)

| ID | Hallazgo | CVSS | Componente | Riesgo |
|----|----------|------|------------|--------|
| H-88 | AI excede arbitraje | 5.8 | `verdict_engine_module.py` | Si modelo produce no-binario, VerdictEngine no valida formato de salida |
| H-89 | Rate limit lógica de escalación | 5.5 | `rate_limiter.rs` L77 | Timestamp se registra ANTES del check de categoría — side-effect en rechazo |
| H-90 | Singletons thread-unsafe | 5.3 | `singleton.py` (3 archivos) | `init_model_manager` sin lock — race condition |
| H-91 | Referencia circular | 5.0 | `gateway-engine.ts` lazy imports | `await import()` en hot path — rendimiento + posibles deadlocks |
| H-92 | Silent failure paths | 5.7 | `encryption.py`, `type_safety.py` | `encrypt()` retorna plaintext, `LIKELY_PROVEN` retorna `verified: True` |
| H-93 | Thread safety inconsistente | 5.2 | 3 singletons Python | Patrón DCL inconsistente — siempre-lock vs double-checked vs sin lock |
| H-94 | Sin rotación de claves | 4.9 | `encryption.py`, `signer.py` | No existe mecanismo para rotar Fernet/ECDSA/HMAC keys |
| H-95 | Merkle cross-language incompatibility | 4.7 | SHA-256 (Py/TS) vs BLAKE3 (Rust) | Cadenas no verificables entre lenguajes |
| H-96 | Fernet sin diversificación | 4.5 | `encryption.py` | Una sola key para todos los datos — sin per-tenant isolation |

### 🟢 BAJOS (Code smells / best practices)

| ID | Hallazgo | CVSS | Componente | Riesgo |
|----|----------|------|------------|--------|
| H-97 | Policy engine duplicado | 3.8 | 3 feature-gates + 2 gateway-engines | Inconsistencia de permisos entre rutas API |
| H-98 | PBKDF2 iteraciones bajas | 3.5 | `encryption.py` | 100K < 600K (OWASP 2024) — merge con H-87 |
| H-99 | Argon2id fallback a PBKDF2 | 3.2 | Rust `crypto.rs` vs Python `encryption.py` | Python nunca usa Argon2id — solo Rust |

---

## 3. GRAFO DE DEPENDENCIAS

```
FASE 1 (H-85 + H-92) ─── Encriptación fail-closed
    │
    ├──→ FASE 2 (H-87 + H-98 + H-99) ─── KDF + iteraciones
    │         │
    │         └──→ FASE 4 (H-94 + H-96) ─── Key rotation + diversificación
    │
    ├──→ FASE 3 (H-79) ─── HMAC/ECDSA signer
    │
FASE 5 (H-78) ─── Multi-tenant (independiente)
    │
    ├──→ FASE 4 (H-96) ─── Fernet diversification depende de tenant
    │
FASE 6 (H-80 + H-81 + H-89 + H-90 + H-93) ─── Safety + Merkle + Singletons
    │
FASE 7 (H-82 + H-83 + H-84 + H-91 + H-95 + H-97 + H-88) ─── Refactoring + deduplicación
```

**Paralelización posible:**
- FASE 1 y FASE 5 pueden ejecutarse en paralelo
- FASE 3 es independiente
- FASE 6 es independiente de FASE 2-4

---

## 4. PLAN DE EJECUCIÓN POR FASES

---

### FASE 1: Fail-Closed Encryption (H-85 + H-92)
**Prioridad:** 🔴 Crítico-Efectivo
**Riesgo breaking change:** 🟡 MEDIO
**Archivos:** `encryption.py`, `type_safety.py`, `_type_safety_proof.py`

#### H-85: Encriptación degrada a plaintext

**Problema actual:**
```python
# encryption.py L246-248
def encrypt(self, plaintext: str) -> str:
    if not self._fernet:
        logger.warning("EncryptionManager: Fernet not available, data stored unencrypted")
        return plaintext  # ← RETORNA PLAINTEXT
```

**Fix propuesto:**
```python
class EncryptionUnavailableError(RuntimeError):
    """Raised when encryption is required but unavailable."""
    pass

def encrypt(self, plaintext: str) -> str:
    """Encrypt a string using Fernet symmetric encryption.
    
    INVARIANT: encrypt() NEVER returns plaintext.
    If Fernet is unavailable:
      - Production: raises EncryptionUnavailableError
      - Dev mode (ZENIC_DEV_MODE=1): returns ZENIC_UNENCRYPTED:base64 wrapper
    """
    if not self._fernet:
        if os.environ.get("ZENIC_DEV_MODE") == "1":
            logger.warning(
                "EncryptionManager: DEV MODE — Fernet unavailable, "
                "data stored with BASE64 wrapper (NOT encrypted). "
                "Set ZENIC_DEV_MODE=0 for production."
            )
            return f"ZENIC_UNENCRYPTED:{base64.b64encode(plaintext.encode()).decode()}"
        raise EncryptionUnavailableError(
            "Fernet encryption is not available. "
            "Install the 'cryptography' package or set ZENIC_DB_PASSPHRASE."
        )
    with self._lock:
        return self._fernet.encrypt(plaintext.encode()).decode()

def decrypt(self, ciphertext: str) -> str:
    """Decrypt a Fernet-encrypted string."""
    # Handle DEV_MODE base64 wrapper
    if ciphertext.startswith("ZENIC_UNENCRYPTED:"):
        if os.environ.get("ZENIC_DEV_MODE") == "1":
            logger.warning("EncryptionManager: Decrypting DEV MODE base64 wrapper — NOT encrypted")
            b64_part = ciphertext[len("ZENIC_UNENCRYPTED:"):]
            return base64.b64decode(b64_part).decode()
        raise EncryptionUnavailableError(
            "Found unencrypted data in non-dev environment. "
            "Data was stored without encryption — this is a security incident."
        )
    if not self._fernet:
        raise EncryptionUnavailableError("Fernet is not available for decryption.")
    with self._lock:
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except Exception as exc:
            raise ValueError(f"Decryption failed: {exc}") from exc
```

**Risk consideration:**
- ⚠️ **Breaking change**: Code that previously called `encrypt()` and got plaintext will now get `EncryptionUnavailableError` in production.
- ✅ Mitigated by: `ZENIC_DEV_MODE=1` escape hatch with `ZENIC_UNENCRYPTED:` prefix.
- ✅ The prefix makes unencrypted data detectable in audit — no silent plaintext.

#### H-92: Silent failure paths

**Problema actual:**
```python
# type_safety.py L399-410 — When Phase 2 times out:
result = TypeSafetyResult(
    verified=True,   # ← MISLEADING — unproven result marked as verified
    status=ProofStatus.LIKELY_PROVEN,
)
```

**Fix propuesto:**
```python
# In both type_safety.py and _type_safety_proof.py:
if phase2_result.status == unknown:
    result = TypeSafetyResult(
        verified=False,  # ← Changed: timeout ≠ proven
        status=ProofStatus.LIKELY_PROVEN,  # Status still says "likely" for logging
    )
```

**Risk consideration:**
- ⚠️ **Breaking change**: Code that checks `verified` will now see `False` for LIKELY_PROVEN results.
- ✅ Mitigated by: Downstream should check `status` field for more nuance. `verified=True` now only for `PROVEN`.

---

### FASE 2: KDF + Iteraciones (H-87 + H-98 + H-99)
**Prioridad:** 🟠 Alto
**Riesgo breaking change:** 🟡 MEDIO (datos existentes no desencriptables con nuevo KDF)
**Archivos:** `encryption.py`

#### H-87 + H-98: PBKDF2 iteraciones demasiado bajas (100K → 600K)

**Fix propuesto:**
```python
class EncryptionManager:
    # OWASP 2024 recommendation: 600K for PBKDF2-SHA256
    DEFAULT_PBKDF2_ITERATIONS = 600_000
    KEY_DERIVATION_VERSION = 2  # v1=100K, v2=600K

    def __init__(
        self,
        master_passphrase: str = "",
        pbkdf2_iterations: int = 0,  # 0 = use DEFAULT
        enable_hardware_binding: bool = True,
    ) -> None:
        self._passphrase = master_passphrase or os.environ.get("ZENIC_DB_PASSPHRASE", "")
        self._pbkdf2_iterations = pbkdf2_iterations or self.DEFAULT_PBKDF2_ITERATIONS
        # ... rest unchanged
```

**Risk consideration:**
- ⚠️ **Breaking change**: Existing Fernet-encrypted data was derived with 100K iterations.
- ✅ **Migration path**: Need `_reencrypt_with_new_iterations()` that decrypts with old key, re-encrypts with new.

#### H-99: Argon2id como KDF preferido

**Fix propuesto:**
```python
def _init_fernet(self) -> None:
    # Try Argon2id first (OWASP preferred)
    try:
        from argon2.low_level import Type, hash_secret_raw
        key_bytes = hash_secret_raw(
            secret=self._passphrase.encode(),
            salt=salt,
            time_cost=3, memory_cost=65536, parallelism=4,
            hash_len=32, type=Type.ID,
        )
        key = base64.urlsafe_b64encode(key_bytes)
        self._kdf_algorithm = "Argon2id"
    except ImportError:
        # Fallback to PBKDF2-SHA256 (600K iterations)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(), length=32,
            salt=salt, iterations=self._pbkdf2_iterations,
        )
        key = base64.urlsafe_b64encode(kdf.derive(self._passphrase.encode()))
        self._kdf_algorithm = "PBKDF2-SHA256"
    
    self._fernet = Fernet(key)
```

---

### FASE 3: HMAC/ECDSA Signer (H-79)
**Prioridad:** 🔴 Crítico
**Riesgo breaking change:** 🟡 MEDIO (licencias HMAC existentes necesitan migración)
**Archivos:** `signer.py`, Rust `signing.rs`, `crypto.rs`

#### H-79: HMAC fallback forja ECDSA

**Fix propuesto — Firmas con prefijo de algoritmo:**
```python
class ECDSASigner:
    ALGO_ECDSA = "ecdsa-p256"
    ALGO_HMAC = "hmac-sha256"
    
    def sign(self, data: str) -> str:
        if not self._use_fallback and self._private_key:
            try:
                signature = self._private_key.sign(
                    data.encode(), ec.ECDSA(hashes.SHA256()),
                )
                return f"{self.ALGO_ECDSA}:{signature.hex()}"
            except Exception as exc:
                logger.error("ECDSA signing failed: %s", exc)
        
        # HMAC fallback — EXPLICITLY tagged, requires DEV MODE in production
        if os.environ.get("ZENIC_DEV_MODE") != "1" and not self._use_fallback:
            raise RuntimeError(
                "ECDSA signing failed and HMAC fallback is disabled in production. "
                "Install the 'cryptography' package."
            )
        
        mac = hmac.new(
            self._fallback_key.encode(), data.encode(), hashlib.sha256,
        ).hexdigest()
        return f"{self.ALGO_HMAC}:{mac}"
    
    def verify(self, data: str, signature_hex: str) -> bool:
        # Parse algorithm prefix
        if ":" in signature_hex:
            algo, sig = signature_hex.split(":", 1)
        else:
            algo = None  # Legacy: try both
            sig = signature_hex
        
        if algo == self.ALGO_ECDSA or (algo is None and not self._use_fallback):
            try:
                self._public_key.verify(
                    bytes.fromhex(sig), data.encode(), ec.ECDSA(hashes.SHA256()),
                )
                return True
            except Exception:
                if algo == self.ALGO_ECDSA:
                    return False  # ECDSA tag → must be ECDSA
        
        if algo == self.ALGO_HMAC or algo is None:
            expected = hmac.new(
                self._fallback_key.encode(), data.encode(), hashlib.sha256,
            ).hexdigest()
            return hmac.compare_digest(expected, sig)
        
        return False
```

**Rust `signing.rs` — Fix timing leak:**
```rust
pub fn verify_signature(data: &str, signature: &str, secret_key: &str) -> bool {
    let expected_hex = hmac_sha256(secret_key, data);
    let expected_bytes = hex_decode(&expected_hex).unwrap_or_default();
    let signature_bytes = hex_decode(signature)
        .unwrap_or_else(|_| vec![0u8; expected_bytes.len().max(32)]);
    constant_time_compare(&expected_bytes, &signature_bytes)
}
```

---

### FASE 4: Key Rotation + Diversificación (H-94 + H-96)
**Prioridad:** 🟡 Medio
**Riesgo breaking change:** 🟢 BAJO (funcionalidad nueva)
**Archivos:** `encryption.py`

#### H-94: Sin rotación de claves

```python
def rotate_key(self, new_passphrase: str) -> None:
    """Rotate the master passphrase and re-encrypt active data."""
    if not self._fernet:
        raise EncryptionUnavailableError("Cannot rotate keys without active encryption")
    
    # Keep old key for decrypt fallback
    self._previous_fernet_key = self._fernet_key
    
    # Derive new key with new salt
    new_salt = secrets.token_bytes(32)
    if self._enable_hw_binding:
        new_salt = self._hardware_bound_salt(new_salt)
    
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32,
        salt=new_salt, iterations=self._pbkdf2_iterations,
    )
    new_key = base64.urlsafe_b64encode(kdf.derive(new_passphrase.encode()))
    
    with self._lock:
        self._fernet = Fernet(new_key)
        self._fernet_key = new_key
        self._passphrase = new_passphrase
    
    self._persist_salt(new_salt)
```

#### H-96: Fernet sin diversificación

```python
def _derive_tenant_key(self, tenant_id: str) -> Fernet:
    """Derive a tenant-specific Fernet key from the master key using HKDF."""
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    
    hkdf = HKDF(
        algorithm=hashes.SHA256(), length=32,
        salt=self._fernet_key, info=tenant_id.encode(),
    )
    tenant_key = base64.urlsafe_b64encode(hkdf.derive(self._passphrase.encode()))
    return Fernet(tenant_key)

def encrypt_for_tenant(self, plaintext: str, tenant_id: str) -> str:
    tenant_fernet = self._derive_tenant_key(tenant_id)
    return tenant_fernet.encrypt(plaintext.encode()).decode()

def decrypt_for_tenant(self, ciphertext: str, tenant_id: str) -> str:
    tenant_fernet = self._derive_tenant_key(tenant_id)
    return tenant_fernet.decrypt(ciphertext.encode()).decode()
```

---

### FASE 5: Multi-Tenant (H-78)
**Prioridad:** 🔴 Crítico
**Riesgo breaking change:** 🟠 ALTO
**Archivos:** `tenant_utils.py`, todos los consumidores

#### H-78: Multi-tenant deshabilitado

```python
# tenant_utils.py — Complete rewrite
"""
Multi-tenant context resolution with fail-closed security.

INVARIANT: resolve_tenant_id() NEVER returns __anonymous__ in production.
           In dev mode (ZENIC_DEV_MODE=1), __anonymous__ is allowed with a warning.
"""
import logging, os, threading
from typing import Optional

logger = logging.getLogger(__name__)

ANONYMOUS_TENANT = "__anonymous__"
_tenant_context = threading.local()

def set_tenant_context(tenant_id: str) -> None:
    if not tenant_id or tenant_id.strip() == "":
        raise ValueError("tenant_id cannot be empty")
    if tenant_id == ANONYMOUS_TENANT:
        if os.environ.get("ZENIC_DEV_MODE") != "1":
            raise ValueError(
                f"Cannot set tenant to {ANONYMOUS_TENANT!r} in production. "
                "Set ZENIC_DEV_MODE=1 for development."
            )
        logger.warning("Tenant context set to anonymous — dev mode only")
    _tenant_context.tenant_id = tenant_id

def clear_tenant_context() -> None:
    _tenant_context.tenant_id = None

def resolve_tenant_id() -> str:
    tenant_id = getattr(_tenant_context, "tenant_id", None)
    if tenant_id is not None:
        return tenant_id
    
    if os.environ.get("ZENIC_DEV_MODE") == "1":
        logger.warning("resolve_tenant_id: No tenant context — using anonymous (dev mode)")
        return ANONYMOUS_TENANT
    
    raise RuntimeError(
        "No tenant context set. Call set_tenant_context(tenant_id) before "
        "accessing tenant-scoped resources. In development, set ZENIC_DEV_MODE=1 "
        "to use anonymous tenant."
    )

def require_tenant() -> str:
    """Strict mode — no anonymous even in dev."""
    tenant_id = getattr(_tenant_context, "tenant_id", None)
    if tenant_id is None or tenant_id == ANONYMOUS_TENANT:
        raise RuntimeError("A real tenant ID is required for this operation.")
    return tenant_id
```

**Risk consideration:**
- ⚠️ **Breaking change — ALTO**: All code calling `resolve_tenant_id()` without context will fail in production.
- ✅ Mitigated by: `ZENIC_DEV_MODE=1` preserves current behavior with warning.

---

### FASE 6: Safety + Merkle + Singletons (H-80 + H-81 + H-89 + H-90 + H-93)
**Prioridad:** 🟠 Alto
**Riesgo breaking change:** 🟢 BAJO

#### H-80: SafetyGate DENY override → DENY persistence

```python
# _gate.py — Add deny-action persistence across resets
_DENY_LOG_DIR = None

def configure_deny_persistence(log_dir: str) -> None:
    global _DENY_LOG_DIR
    _DENY_LOG_DIR = log_dir

def reset_safety_gate() -> None:
    global _default_safety_gate
    # Save denied actions before reset
    if _default_safety_gate is not None and _DENY_LOG_DIR:
        denied = list(_default_safety_gate._denied_actions)
        try:
            with open(os.path.join(_DENY_LOG_DIR, ".safety-denied-actions.json"), "w") as f:
                json.dump({"denied_actions": denied, "ts": time.time()}, f)
        except Exception as exc:
            logger.error("Failed to persist denied actions: %s", exc)
    with _safety_gate_lock:
        _default_safety_gate = None

def get_default_safety_gate() -> SafetyGate:
    global _default_safety_gate
    if _default_safety_gate is None:
        with _safety_gate_lock:
            if _default_safety_gate is None:
                gate = SafetyGate()
                # Restore denied actions from persistence
                if _DENY_LOG_DIR:
                    deny_path = os.path.join(_DENY_LOG_DIR, ".safety-denied-actions.json")
                    if os.path.exists(deny_path):
                        try:
                            with open(deny_path) as f:
                                data = json.load(f)
                            for action_id in data.get("denied_actions", []):
                                gate._denied_actions.add(action_id)
                            logger.info("Restored %d denied actions from persistence", len(gate._denied_actions))
                        except Exception as exc:
                            logger.warning("Failed to restore denied actions: %s", exc)
                _default_safety_gate = gate
    return _default_safety_gate
```

#### H-81: Merkle ledger persistence

```python
# _merkle.py — Add flush callback (same pattern as TS merkle-audit.ts)
class AuditMerkleChain:
    def __init__(self, persist_callback=None, flush_interval=100) -> None:
        self._last_hash = self.GENESIS_HASH
        self._lock = threading.Lock()
        self._persist_callback = persist_callback
        self._pending_entries: List[AuditEntry] = []
        self._flush_interval = flush_interval
    
    def seal(self, entry: AuditEntry) -> str:
        with self._lock:
            h = self.compute_hash(entry)
            entry.prev_hash = self._last_hash
            entry.merkle_hash = h
            self._last_hash = h
            self._pending_entries.append(entry)
            
            if len(self._pending_entries) >= self._flush_interval:
                self._flush()
            return h
    
    def _flush(self) -> None:
        if self._persist_callback and self._pending_entries:
            try:
                self._persist_callback(list(self._pending_entries), self._last_hash)
                self._pending_entries.clear()
            except Exception as exc:
                logger.error("MerkleChain: Flush failed: %s", exc)
```

#### H-90 + H-93: DRY Singleton pattern

```python
# src/core/shared/singleton.py — NEW FILE
class Singleton:
    """Thread-safe singleton with double-checked locking."""
    def __init__(self, factory, name="") -> None:
        self._factory = factory
        self._name = name or factory.__qualname__
        self._instance = None
        self._lock = threading.Lock()
    
    def get(self):
        if self._instance is None:
            with self._lock:
                if self._instance is None:
                    self._instance = self._factory()
        return self._instance
    
    def init(self, factory):
        with self._lock:
            if self._instance is not None:
                raise RuntimeError(f"{self._name} already initialized. Call reset() first.")
            self._factory = factory
            self._instance = self._factory()
        return self._instance
    
    def reset(self):
        with self._lock:
            self._instance = None
```

#### H-89: Rate limit timestamp (Rust fix)

```rust
// rate_limiter.rs — Only append timestamps AFTER all checks pass
pub fn check(action_type: &str, category: ActionCategory) -> Option<String> {
    let mut state = RATE_LIMITER.lock().unwrap_or_else(|e| e.into_inner());
    let now = Instant::now();
    
    // ALL checks first — no side effects
    // Per-minute check
    let ts = state.timestamps.entry(action_type.to_string()).or_default();
    ts.retain(|t| now.duration_since(*t) < Duration::from_secs(60));
    if ts.len() >= state.max_per_minute {
        return Some(format!("Rate limited: {} exceeded {}/min", action_type, state.max_per_minute));
    }
    
    // Category checks...
    // (validation only — no appends yet)
    
    // ALL checks passed — NOW append timestamps
    ts.push(now);
    // category_timestamps push...
    None
}
```

---

### FASE 7: Refactoring + Deduplicación (H-82 + H-83 + H-84 + H-91 + H-95 + H-97 + H-88)
**Prioridad:** 🟡 Medio
**Riesgo breaking change:** 🟡 MEDIO

#### H-83: God Object orchestrator → Phase pattern

```python
# orchestrator/phases/__init__.py
class OrchestratorPhase(ABC):
    @abstractmethod
    def initialize(self, ctx: OrchestratorContext) -> None: ...
    @abstractmethod
    def shutdown(self) -> None: ...

# 8 phases extracted from __init__
class CommonStatePhase(OrchestratorPhase): ...
class PipelinePhase(OrchestratorPhase): ...
class AIArchitecturePhase(OrchestratorPhase): ...
class ExtendedPhase(OrchestratorPhase): ...
class DecomposedPhase(OrchestratorPhase): ...
class AgentFrameworkPhase(OrchestratorPhase): ...
class GodLevelPhase(OrchestratorPhase): ...
class ScanPhase(OrchestratorPhase): ...
```

#### H-84 + H-97: Deduplicación

- **Feature Gates**: Consolidar 3 → 1 (mantener pricing-engine, eliminar subscription, renombrar exports)
- **Gateway Engine**: Eliminar versión funcional, redirigir API route al engine con pipeline completo
- **Z3 Type Safety**: Eliminar `_type_safety_proof.py`, mantener solo `type_safety.py`

#### H-88: Verdict output validation

```python
VALID_VERDICTS = {"YES", "NO"}

def _validate_ai_verdict(self, raw_output: str) -> str:
    clean = raw_output.strip().upper()
    if clean in VALID_VERDICTS:
        return clean
    first_word = clean.split()[0] if clean.split() else ""
    if first_word in VALID_VERDICTS:
        logger.warning("AI added extra output. Using first word: %s", first_word)
        return first_word
    logger.error("AI produced non-binary output: %s. Defaulting to NO.", raw_output[:100])
    return "NO"
```

#### H-95: Merkle cross-language

```python
# _merkle.py — Support configurable hash algorithm
class AuditMerkleChain:
    def __init__(self, hash_algorithm="sha256"):
        if hash_algorithm == "blake3":
            try:
                import blake3 as _blake3
                self._hash_fn = lambda data: _blake3.blake3(data).hexdigest()
            except ImportError:
                self._hash_fn = lambda data: hashlib.sha256(data).hexdigest()
                hash_algorithm = "sha256"
        else:
            self._hash_fn = lambda data: hashlib.sha256(data).hexdigest()
```

---

## 5. RESUMEN DE RIESGOS

### Breaking Changes (requieren plan de migración)

| Hallazgo | Breaking? | Mitigación |
|----------|-----------|------------|
| H-85 (encrypt fail-closed) | 🟡 Sí | `ZENIC_DEV_MODE=1` + `ZENIC_UNENCRYPTED:` prefix |
| H-87 (PBKDF2 600K) | 🟡 Sí | Re-encrypt migration tool |
| H-79 (ECDSA/HMAC prefix) | 🟡 Sí | Legacy prefixless support + deprecation window |
| H-78 (multi-tenant) | 🟠 Alto | `ZENIC_DEV_MODE=1` preserves current behavior |

### Sin Cambio Necesario (ya corregido)

| Hallazgo | Estado |
|----------|--------|
| H-86 (Static Fernet salt) | FIX SEC-6 ya aplicado — salt instance-unique |
| H-98 (PBKDF2 iterations) | Merge con H-87 — misma solución |

---

## 6. CRONOGRAMA

```
Semana 1:  FASE 1 (H-85 + H-92) — Fail-closed encryption
Semana 1:  FASE 3 (H-79) — ECDSA/HMAC signer        [PARALELO]
Semana 2:  FASE 2 (H-87 + H-98 + H-99) — KDF + Argon2id
Semana 2:  FASE 5 (H-78) — Multi-tenant              [PARALELO]
Semana 3:  FASE 6 (H-80 + H-81 + H-89 + H-90 + H-93) — Safety + Singletons
Semana 4:  FASE 4 (H-94 + H-96) — Key rotation + diversification
Semana 5:  FASE 7 (H-82 + H-83 + H-84 + H-91 + H-95 + H-97 + H-88) — Refactoring
```

---

## 7. INVARIANTES FUNDAMENTALES (post-remediación)

1. **INVARIANT 1**: `encrypt()` NUNCA retorna plaintext en producción
2. **INVARIANT 2**: ECDSA y HMAC son algoritmos DISTINTOS con prefijo explícito
3. **INVARIANT 3**: DENY es absoluto — persiste a través de resets
4. **INVARIANT 4**: Sin tenant = denegado (fail-closed)
5. **INVARIANT 5**: Merkle chain se persiste periódicamente
6. **INVARIANT 6**: PBKDF2-SHA256 ≥ 600K iteraciones (o Argon2id)
7. **INVARIANT 7**: AI verdict es estrictamente binario (YES/NO)
8. **INVARIANT 8**: `verified=True` solo para PROVEN (no LIKELY_PROVEN)
