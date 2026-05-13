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
    - PBKDF2-SHA256 key derivation with hardware binding
    - Key rotation and re-encryption support

    When SQLCipher is available (via pysqlcipher3 or sqlcipher3),
    all databases are encrypted with AES-256. When not available,
    Fernet provides application-level encryption for sensitive fields.
    """

    def __init__(
        self,
        master_passphrase: str = "",
        pbkdf2_iterations: int = 100_000,
        enable_hardware_binding: bool = True,
    ) -> None:
        self._passphrase = master_passphrase or os.environ.get("ZENIC_DB_PASSPHRASE", "")
        self._pbkdf2_iterations = pbkdf2_iterations
        self._enable_hw_binding = enable_hardware_binding
        self._fernet = None
        self._fernet_key: bytes = b""
        self._lock = threading.Lock()
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
        """Initialize Fernet encryption with derived key."""
        if not self._fernet_available:
            return

        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

        # Derive Fernet key from passphrase
        salt = b"zenic-agents-fernet-salt-v1"
        if self._enable_hw_binding:
            salt = self._hardware_bound_salt(salt)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=self._pbkdf2_iterations,
        )
        key = base64.urlsafe_b64encode(kdf.derive(self._passphrase.encode()))
        self._fernet = Fernet(key)
        self._fernet_key = key
        logger.info("EncryptionManager: Fernet initialized (iterations=%d)", self._pbkdf2_iterations)

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
            Base64-encoded encrypted string, or the original if encryption unavailable.
        """
        if not self._fernet:
            logger.warning("EncryptionManager: Fernet not available, data stored unencrypted")
            return plaintext

        with self._lock:
            return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a Fernet-encrypted string.

        Args:
            ciphertext: The Base64-encoded encrypted string.

        Returns:
            Decrypted plaintext string.
        """
        if not self._fernet:
            logger.warning("EncryptionManager: Fernet not available, returning raw data")
            return ciphertext

        with self._lock:
            try:
                return self._fernet.decrypt(ciphertext.encode()).decode()
            except Exception as exc:
                logger.error("EncryptionManager: Decryption failed: %s", exc)
                raise ValueError(f"Decryption failed: {exc}") from exc

    def encrypt_dict(self, data: Dict[str, Any], sensitive_keys: Optional[list] = None) -> Dict[str, Any]:
        """Encrypt sensitive fields in a dictionary.

        Args:
            data: Dictionary with potentially sensitive fields.
            sensitive_keys: List of keys whose values should be encrypted.

        Returns:
            Dictionary with sensitive values encrypted.
        """
        if not self._fernet or not sensitive_keys:
            return data

        result = dict(data)
        for key in sensitive_keys:
            if key in result and isinstance(result[key], str):
                result[key] = self.encrypt(result[key])
                result[f"_{key}_encrypted"] = True
        return result

    def decrypt_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Decrypt all encrypted fields in a dictionary.

        Args:
            data: Dictionary with encrypted values.

        Returns:
            Dictionary with decrypted values.
        """
        if not self._fernet:
            return data

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
            pw = passphrase or self._passphrase or "default-key"
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
            key_derivation="PBKDF2-SHA256",
            iterations=self._pbkdf2_iterations,
        )


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
