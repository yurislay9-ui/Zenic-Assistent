"""
Zenic-Agents Asistente - Defense in Depth Layer 3: Encryption (Phase 6.2)

Layer 3: SQLCipher + Fernet + PBKDF2 encryption suite.
Provides encrypted storage, key derivation, and data-at-rest protection.

Components:
- EncryptionManager: Central encryption/decryption orchestrator
- Key derivation: PBKDF2-SHA256 with configurable iterations
- Fernet symmetric encryption for sensitive data
- SQLCipher integration for encrypted databases
- Hardware binding: encryption keys tied to hardware fingerprint
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from src.core.shared.sqlcipher_helper import (
    get_sqlcipher_connection as _helper_get_conn,
    is_sqlcipher_available,
    HAS_SQLCIPHER as _HAS_SQLCIPHER_HELPER,
)

logger = logging.getLogger(__name__)


class EncryptionUnavailableError(RuntimeError):
    """Raised when encryption is required but unavailable."""
    pass


class EncryptionLevel(str, Enum):
    """Level of encryption active."""
    NONE = "none"
    FERNET = "fernet"           # Symmetric encryption for sensitive data
    SQLCIPHER = "sqlcipher"     # Full database encryption
    FULL = "full"               # Both Fernet + SQLCipher


@dataclass
class EncryptionStatus:
    """Current encryption status."""
    level: EncryptionLevel
    fernet_available: bool
    sqlcipher_available: bool
    hardware_bound: bool
    key_derivation: str
    iterations: int


class EncryptionManager:
    """Defense in Depth Layer 3: Encryption orchestrator.

    Manages all encryption operations:
    - Fernet symmetric encryption for secrets, tokens, PII
    - SQLCipher for encrypted database storage
    - Argon2id (preferred) / PBKDF2-SHA256 key derivation with hardware binding
    - Key rotation and re-encryption support

    When SQLCipher is available (via pysqlcipher3 or sqlcipher3),
    all databases are encrypted with AES-256. When not available,
    Fernet provides application-level encryption for sensitive fields.
    """

    DEFAULT_PBKDF2_ITERATIONS: int = 600_000
    KEY_DERIVATION_VERSION: int = 2

    def __init__(
        self,
        master_passphrase: str = "",
        pbkdf2_iterations: int = 0,
        enable_hardware_binding: bool = True,
    ) -> None:
        self._passphrase = master_passphrase or os.environ.get("ZENIC_DB_PASSPHRASE", "")
        self._pbkdf2_iterations = pbkdf2_iterations or self.DEFAULT_PBKDF2_ITERATIONS
        self._enable_hw_binding = enable_hardware_binding
        self._fernet = None
        self._fernet_key: bytes = b""
        self._lock = threading.Lock()
        self._kdf_algorithm: str = "PBKDF2-SHA256"
        self._previous_fernet_key: Optional[bytes] = None
        self._previous_fernet: Optional[Any] = None
        self._sqlcipher_available = False

        # Check Fernet availability
        self._fernet_available = self._check_fernet()
        if self._fernet_available and self._passphrase:
            self._init_fernet()

        # Check SQLCipher availability
        self._sqlcipher_available = self._check_sqlcipher()

    def _check_fernet(self) -> bool:
        """Check if cryptography.fernet is available."""
        try:
            from cryptography.fernet import Fernet
            return True
        except ImportError:
            logger.debug("EncryptionManager: cryptography not available, Fernet disabled")
            return False

    def _check_sqlcipher(self) -> bool:
        """Check if SQLCipher is available via the shared helper."""
        self._sqlcipher_available = is_sqlcipher_available()
        if not self._sqlcipher_available:
            logger.debug("EncryptionManager: SQLCipher not available, database encryption disabled")
        return self._sqlcipher_available

    def _init_fernet(self) -> None:
        """Initialize Fernet encryption with derived key.

        Tries Argon2id first (OWASP preferred), falls back to
        PBKDF2-SHA256 with 600K iterations (OWASP 2024 minimum).
        """
        if not self._fernet_available:
            return

        from cryptography.fernet import Fernet

        salt = self._get_or_create_salt()
        if self._enable_hw_binding:
            salt = self._hardware_bound_salt(salt)

        # Try Argon2id first (OWASP preferred KDF)
        try:
            import argon2

            key_bytes = argon2.low_level.hash_secret_raw(
                secret=self._passphrase.encode(),
                salt=salt,
                time_cost=3,          # OWASP recommendation
                memory_cost=65536,    # 64 MB
                parallelism=4,
                hash_len=32,
                type=argon2.low_level.Type.ID,
            )
            key = base64.urlsafe_b64encode(key_bytes)
            self._kdf_algorithm = "Argon2id"
            logger.info("EncryptionManager: Fernet initialized with Argon2id")
        except ImportError:
            # Fallback to PBKDF2-SHA256 (600K iterations, OWASP 2024 minimum)
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=self._pbkdf2_iterations,
            )
            key = base64.urlsafe_b64encode(kdf.derive(self._passphrase.encode()))
            self._kdf_algorithm = "PBKDF2-SHA256"
            logger.info(
                "EncryptionManager: Fernet initialized with PBKDF2-SHA256 (iterations=%d)",
                self._pbkdf2_iterations,
            )
        except Exception as exc:
            # Argon2id available but failed — fall back to PBKDF2
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

            logger.warning("EncryptionManager: Argon2id failed (%s), falling back to PBKDF2-SHA256", exc)
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=self._pbkdf2_iterations,
            )
            key = base64.urlsafe_b64encode(kdf.derive(self._passphrase.encode()))
            self._kdf_algorithm = "PBKDF2-SHA256"
            logger.info(
                "EncryptionManager: Fernet initialized with PBKDF2-SHA256 (iterations=%d)",
                self._pbkdf2_iterations,
            )

        self._fernet = Fernet(key)
        self._fernet_key = key

    def reencrypt_with_new_kdf(
        self,
        old_iterations: int = 100_000,
        old_kdf: str = "PBKDF2-SHA256",
    ) -> None:
        """Re-encrypt data with the current KDF parameters.

        This is needed when migrating from v1 (100K PBKDF2) to v2 (600K/Argon2id).
        Call this after rotating the key to re-derive with stronger parameters.

        NOTE: This re-derives the Fernet key with the current KDF settings.
        Data encrypted with the OLD key must be decrypted BEFORE calling this,
        then re-encrypted AFTER. This method only changes the key derivation.

        Args:
            old_iterations: Previous PBKDF2 iteration count (default: 100K for v1).
            old_kdf: Previous KDF algorithm name.
        """
        logger.info(
            "EncryptionManager: Re-encrypting with new KDF (was: %s/%d, now: %s)",
            old_kdf, old_iterations, self._kdf_algorithm,
        )
        # Re-derive key with current settings — this replaces the existing Fernet key
        self._init_fernet()

    def _hardware_bound_salt(self, base_salt: bytes) -> bytes:
        """Create a hardware-bound salt by combining base salt with hardware fingerprint.

        The hardware fingerprint includes CPU, disk, and memory identifiers,
        making the encryption keys tied to the specific machine.
        """
        try:
            fingerprint = self._get_hardware_fingerprint()
            combined = base_salt + fingerprint.encode()
            return hashlib.sha256(combined).digest()
        except Exception:
            return base_salt

    def _get_or_create_salt(self) -> bytes:
        """Generate or load a unique salt for this instance.

        The salt is persisted in the data directory so that Fernet keys
        remain consistent across restarts. If no salt file exists, a new
        random 32-byte salt is generated and saved with restricted permissions.
        This replaces the previous hardcoded static salt.
        """
        try:
            from src.core.shared.db_initializer import get_data_dir
            data_dir = get_data_dir()
        except Exception:
            data_dir = os.path.expanduser("~/.zenic_agents/data")
            os.makedirs(data_dir, exist_ok=True)

        salt_path = os.path.join(data_dir, ".fernet-salt")

        # Load existing salt if available and valid
        if os.path.exists(salt_path):
            try:
                with open(salt_path, "rb") as f:
                    salt = f.read()
                if len(salt) >= 16:
                    return salt
            except Exception as exc:
                logger.debug("EncryptionManager: Failed to read salt file: %s", exc)

        # Generate new random salt
        salt = secrets.token_bytes(32)
        try:
            with open(salt_path, "wb") as f:
                f.write(salt)
            os.chmod(salt_path, 0o600)
            logger.info("EncryptionManager: Generated new instance-unique Fernet salt")
        except Exception as exc:
            logger.warning("EncryptionManager: Failed to persist salt file: %s", exc)

        return salt

    @staticmethod
    def _get_hardware_fingerprint() -> str:
        """Generate a hardware fingerprint from system identifiers."""
        components: list = []

        # CPU info
        try:
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if line.startswith("model name"):
                        components.append(line.strip())
                        break
        except (FileNotFoundError, PermissionError):
            pass

        # Machine ID (Linux)
        for path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
            try:
                with open(path, "r") as f:
                    components.append(f.read().strip())
                    break
            except (FileNotFoundError, PermissionError):
                continue

        # Disk serial
        try:
            import subprocess
            result = subprocess.run(
                ["lsblk", "-ndo", "SERIAL"], capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0:
                serials = [s.strip() for s in result.stdout.split("\n") if s.strip()]
                if serials:
                    components.append(serials[0])
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Memory info
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        components.append(line.strip())
                        break
        except (FileNotFoundError, PermissionError):
            pass

        fingerprint = "|".join(components) if components else "default-fingerprint"
        return hashlib.sha256(fingerprint.encode()).hexdigest()[:32]

    # ── Public API ─────────────────────────────────────────

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string using Fernet symmetric encryption.

        Args:
            plaintext: The string to encrypt.

        Returns:
            Base64-encoded encrypted string.

        Raises:
            EncryptionUnavailableError: If Fernet is not available and not in dev mode.
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
        """Decrypt a Fernet-encrypted string.

        Args:
            ciphertext: The Base64-encoded encrypted string.

        Returns:
            Decrypted plaintext string.

        Raises:
            EncryptionUnavailableError: If Fernet is not available or unencrypted data found in production.
        """
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

        # Try current key first, then previous key (for rotation migration)
        with self._lock:
            try:
                return self._fernet.decrypt(ciphertext.encode()).decode()
            except Exception:
                if self._previous_fernet is not None:
                    try:
                        return self._previous_fernet.decrypt(ciphertext.encode()).decode()
                    except Exception:
                        pass
                logger.error("EncryptionManager: Decryption failed with both current and previous keys")
                raise ValueError(f"Decryption failed with both current and previous keys")

    def encrypt_dict(self, data: Dict[str, Any], sensitive_keys: Optional[list] = None) -> Dict[str, Any]:
        """Encrypt sensitive fields in a dictionary."""
        if not sensitive_keys:
            return data

        if not self._fernet:
            if os.environ.get("ZENIC_DEV_MODE") == "1":
                logger.warning("EncryptionManager: DEV MODE — encrypt_dict without Fernet, skipping encryption")
                return data
            raise EncryptionUnavailableError(
                "Fernet encryption is not available for encrypt_dict."
            )

        result = dict(data)
        for key in sensitive_keys:
            if key in result and isinstance(result[key], str):
                result[key] = self.encrypt(result[key])
                result[f"_{key}_encrypted"] = True
        return result

    def decrypt_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Decrypt all encrypted fields in a dictionary."""
        if not self._fernet:
            # Check if any values start with ZENIC_UNENCRYPTED: prefix (dev mode)
            has_unencrypted = any(
                isinstance(v, str) and v.startswith("ZENIC_UNENCRYPTED:")
                for v in data.values()
            )
            if has_unencrypted and os.environ.get("ZENIC_DEV_MODE") == "1":
                result = dict(data)
                encrypted_markers = [k for k in result if k.endswith("_encrypted") and result[k]]
                for marker in encrypted_markers:
                    key = marker.replace("_encrypted", "").lstrip("_")
                    if key in result and isinstance(result[key], str):
                        result[key] = self.decrypt(result[key])
                        del result[marker]
                return result
            raise EncryptionUnavailableError(
                "Fernet is not available for decrypt_dict."
            )

        result = dict(data)
        encrypted_markers = [k for k in result if k.endswith("_encrypted") and result[k]]
        for marker in encrypted_markers:
            key = marker.replace("_encrypted", "").lstrip("_")
            if key in result and isinstance(result[key], str):
                result[key] = self.decrypt(result[key])
                del result[marker]
        return result

    def get_sqlcipher_connection(
        self, db_path: str, passphrase: Optional[str] = None,
    ) -> Optional[Any]:
        """Get an encrypted SQLCipher database connection.

        Args:
            db_path: Path to the database file.
            passphrase: Encryption passphrase (defaults to master passphrase).

        Returns:
            SQLCipher connection, or None if SQLCipher unavailable.
        """
        if not self._sqlcipher_available:
            logger.debug("EncryptionManager: SQLCipher unavailable")
            return None

        try:
            # FIX SEC-5: Removed "default-key" fallback. SQLCipher requires a real passphrase.
            pw = passphrase or self._passphrase or os.environ.get("ZENIC_DB_PASSPHRASE")
            if not pw:
                if os.environ.get("NODE_ENV") == "production":
                    raise RuntimeError(
                        "ZENIC_DB_PASSPHRASE is required for SQLCipher in production. "
                        "Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
                    )
                logger.warning(
                    "EncryptionManager: No passphrase configured for SQLCipher. "
                    "Returning unencrypted connection (no false sense of security)."
                )
                return None
            if len(pw) < 32:
                logger.warning(
                    "EncryptionManager: SQLCipher passphrase is less than 32 characters. "
                    "Consider using a longer passphrase for production."
                )
            conn = _helper_get_conn(db_path, pw, verify=True)
            return conn
        except Exception as exc:
            logger.error("EncryptionManager: SQLCipher connection failed: %s", exc)
            return None

    def get_status(self) -> EncryptionStatus:
        """Get current encryption status."""
        hw_bound = self._enable_hw_binding and bool(self._passphrase)
        if self._fernet_available and self._sqlcipher_available:
            level = EncryptionLevel.FULL
        elif self._sqlcipher_available:
            level = EncryptionLevel.SQLCIPHER
        elif self._fernet_available:
            level = EncryptionLevel.FERNET
        else:
            level = EncryptionLevel.NONE

        return EncryptionStatus(
            level=level,
            fernet_available=self._fernet_available,
            sqlcipher_available=self._sqlcipher_available,
            hardware_bound=hw_bound,
            key_derivation=f"{self._kdf_algorithm}-v{self.KEY_DERIVATION_VERSION}",
            iterations=self._pbkdf2_iterations,
        )

    # ── Key Rotation ───────────────────────────────────────

    def rotate_key(self, new_passphrase: str) -> None:
        """Rotate the master passphrase and re-derive the Fernet key.

        After rotation, both old and new keys are available for decrypt():
        - New key is used for encrypt()
        - Old key is kept for decrypt() fallback (supports gradual migration)

        INVARIANT: rotate_key() never leaves the EncryptionManager in a broken
        state. If key derivation fails, the old key remains active.

        Args:
            new_passphrase: The new master passphrase.

        Raises:
            EncryptionUnavailableError: If no Fernet is currently active.
            ValueError: If the new passphrase is empty.
        """
        if not self._fernet:
            raise EncryptionUnavailableError("Cannot rotate keys without active encryption")

        if not new_passphrase or new_passphrase.strip() == "":
            raise ValueError("New passphrase cannot be empty")

        # Keep old key for decrypt fallback
        self._previous_fernet_key: Optional[bytes] = self._fernet_key
        self._previous_fernet: Optional[Any] = self._fernet

        try:
            # Derive new key with new passphrase
            from cryptography.fernet import Fernet
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

            new_salt = secrets.token_bytes(32)
            if self._enable_hw_binding:
                new_salt = self._hardware_bound_salt(new_salt)

            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=new_salt,
                iterations=self._pbkdf2_iterations,
            )
            new_key = base64.urlsafe_b64encode(kdf.derive(new_passphrase.encode()))

            with self._lock:
                self._fernet = Fernet(new_key)
                self._fernet_key = new_key
                self._passphrase = new_passphrase

            # Persist new salt
            self._persist_salt(new_salt)

            logger.info(
                "EncryptionManager: Key rotation completed (algorithm=%s, iterations=%d)",
                self._kdf_algorithm, self._pbkdf2_iterations,
            )
        except Exception as exc:
            # Rollback — restore old key
            logger.error("EncryptionManager: Key rotation failed: %s — rolling back", exc)
            self._fernet = self._previous_fernet
            self._fernet_key = self._previous_fernet_key
            raise

    def _persist_salt(self, salt: bytes) -> None:
        """Persist a salt value to the data directory."""
        try:
            from src.core.shared.db_initializer import get_data_dir
            data_dir = get_data_dir()
        except Exception:
            data_dir = os.path.expanduser("~/.zenic_agents/data")
            os.makedirs(data_dir, exist_ok=True)

        salt_path = os.path.join(data_dir, ".fernet-salt")
        try:
            with open(salt_path, "wb") as f:
                f.write(salt)
            os.chmod(salt_path, 0o600)
        except Exception as exc:
            logger.warning("EncryptionManager: Failed to persist salt: %s", exc)

    # ── Per-Tenant Key Diversification ──────────────────────

    def _derive_tenant_key(self, tenant_id: str) -> "Fernet":
        """Derive a tenant-specific Fernet key from the master key.

        Uses HKDF-SHA256 with tenant_id as info parameter.
        Each tenant gets a unique encryption key, preventing
        cross-tenant decryption even if the master key is shared.

        Args:
            tenant_id: The tenant identifier.

        Returns:
            A Fernet instance with a tenant-specific key.
        """
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from cryptography.hazmat.primitives import hashes

        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self._fernet_key,  # Master key as salt
            info=tenant_id.encode(),  # Tenant ID as context
        )
        tenant_key = base64.urlsafe_b64encode(hkdf.derive(self._passphrase.encode()))
        return Fernet(tenant_key)

    def encrypt_for_tenant(self, plaintext: str, tenant_id: str) -> str:
        """Encrypt data with a tenant-specific key.

        Each tenant gets a derived key via HKDF, ensuring that
        data encrypted for one tenant cannot be decrypted by another,
        even if they share the same master passphrase.

        Args:
            plaintext: The string to encrypt.
            tenant_id: The tenant identifier.

        Returns:
            Base64-encoded encrypted string.

        Raises:
            EncryptionUnavailableError: If Fernet is not available.
            ValueError: If tenant_id is empty.
        """
        if not self._fernet:
            raise EncryptionUnavailableError("Fernet not available for tenant encryption")
        if not tenant_id or tenant_id.strip() == "":
            raise ValueError("tenant_id cannot be empty for tenant-specific encryption")

        tenant_fernet = self._derive_tenant_key(tenant_id)
        return tenant_fernet.encrypt(plaintext.encode()).decode()

    def decrypt_for_tenant(self, ciphertext: str, tenant_id: str) -> str:
        """Decrypt data with a tenant-specific key.

        Args:
            ciphertext: The Base64-encoded encrypted string.
            tenant_id: The tenant identifier.

        Returns:
            Decrypted plaintext string.

        Raises:
            EncryptionUnavailableError: If Fernet is not available.
            ValueError: If tenant_id is empty or decryption fails.
        """
        if not self._fernet:
            raise EncryptionUnavailableError("Fernet not available for tenant decryption")
        if not tenant_id or tenant_id.strip() == "":
            raise ValueError("tenant_id cannot be empty for tenant-specific decryption")

        tenant_fernet = self._derive_tenant_key(tenant_id)
        try:
            return tenant_fernet.decrypt(ciphertext.encode()).decode()
        except Exception as exc:
            raise ValueError(f"Tenant decryption failed: {exc}") from exc


# ── Singleton ─────────────────────────────────────────────

_encryption_manager: Optional[EncryptionManager] = None
_lock = threading.Lock()


def get_encryption_manager(**kwargs: Any) -> EncryptionManager:
    """Get or create the global EncryptionManager instance."""
    global _encryption_manager
    with _lock:
        if _encryption_manager is None:
            _encryption_manager = EncryptionManager(**kwargs)
        return _encryption_manager


def reset_encryption_manager() -> None:
    """Reset the global EncryptionManager (for testing)."""
    global _encryption_manager
    _encryption_manager = None
