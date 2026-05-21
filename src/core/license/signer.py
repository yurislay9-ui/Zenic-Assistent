"""
Zenic-Agents Asistente - ECDSA Signing & Verification (Phase 6.3)

Cryptographic signing and verification for licenses using ECDSA.
Supports both the `cryptography` library (preferred) and a
pure-Python fallback for environments without it.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class ECDSASigner:
    """ECDSA cryptographic signing for licenses.

    Uses the `cryptography` library when available for proper
    ECDSA with NIST P-256 curve. Falls back to HMAC-SHA256
    when the library is not installed.

    The fallback is NOT cryptographically equivalent to ECDSA
    but provides integrity verification in constrained environments.

    Signatures are prefixed with the algorithm used:
        "ecdsa-p256:<hex>" for ECDSA signatures
        "hmac-sha256:<hex>" for HMAC fallback signatures
    This prevents an attacker from forging HMAC signatures that
    pass ECDSA verification, and vice-versa.
    """

    ALGO_ECDSA = "ecdsa-p256"
    ALGO_HMAC = "hmac-sha256"

    def __init__(self, private_key_pem: str = "", public_key_pem: str = "") -> None:
        self._private_key = None
        self._public_key = None
        self._use_fallback = True
        # FIX SEC-4: Removed hardcoded fallback key. Use env var or ephemeral key.
        signing_key = os.environ.get("ZENIC_SIGNING_KEY")
        if signing_key:
            self._fallback_key = signing_key
        elif os.environ.get("NODE_ENV") == "production":
            raise RuntimeError(
                "ZENIC_SIGNING_KEY is required in production when "
                "ECDSA is unavailable. Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        else:
            self._fallback_key = secrets.token_hex(32)
            logger.warning(
                "ECDSASigner: No ZENIC_SIGNING_KEY configured. "
                "Using ephemeral HMAC key — signatures will NOT survive restart. "
                "Set ZENIC_SIGNING_KEY for persistent signing."
            )

        if private_key_pem or public_key_pem:
            self._try_load_keys(private_key_pem, public_key_pem)
        else:
            # Try generating or loading default keys
            self._try_default_keys()

    def _try_load_keys(self, private_pem: str, public_pem: str) -> None:
        """Try loading ECDSA keys from PEM format."""
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import ec

            if private_pem:
                self._private_key = serialization.load_pem_private_key(
                    private_pem.encode(), password=None,
                )
            if public_pem:
                self._public_key = serialization.load_pem_public_key(
                    public_pem.encode(),
                )
            self._use_fallback = False
            logger.info("ECDSASigner: Loaded ECDSA keys")
        except ImportError:
            logger.warning("ECDSASigner: cryptography not available, using HMAC fallback")
        except Exception as exc:
            logger.warning("ECDSASigner: Key loading failed: %s, using HMAC fallback", exc)

    def _try_default_keys(self) -> None:
        """Try loading default keys from environment or file."""
        # Check for key files in standard locations
        key_dir = os.path.expanduser("~/.zenic-license")
        priv_path = os.path.join(key_dir, "signing_key.pem")
        pub_path = os.path.join(key_dir, "signing_pub.pem")

        if os.path.exists(priv_path) and os.path.exists(pub_path):
            try:
                with open(priv_path, "r") as f:
                    priv_pem = f.read()
                with open(pub_path, "r") as f:
                    pub_pem = f.read()
                self._try_load_keys(priv_pem, pub_pem)
                return
            except Exception as exc:
                logger.debug("ECDSASigner: Default key load failed: %s", exc)

        # Generate new keys if cryptography is available
        self._try_generate_keys()

    def _try_generate_keys(self) -> None:
        """Try generating new ECDSA key pair."""
        try:
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.primitives import serialization

            self._private_key = ec.generate_private_key(ec.SECP256R1())
            self._public_key = self._private_key.public_key()
            self._use_fallback = False

            # Save to default location
            key_dir = os.path.expanduser("~/.zenic-license")
            os.makedirs(key_dir, exist_ok=True)

            priv_pem = self._private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            pub_pem = self._public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )

            priv_path = os.path.join(key_dir, "signing_key.pem")
            pub_path = os.path.join(key_dir, "signing_pub.pem")

            with open(priv_path, "wb") as f:
                f.write(priv_pem)
            os.chmod(priv_path, 0o600)

            with open(pub_path, "wb") as f:
                f.write(pub_pem)

            logger.info("ECDSASigner: Generated and saved new ECDSA key pair")
        except ImportError:
            logger.warning("ECDSASigner: cryptography not available, using HMAC fallback")
        except Exception as exc:
            logger.warning("ECDSASigner: Key generation failed: %s, using HMAC fallback", exc)

    def sign(self, data: str) -> str:
        """Sign data and return the signature as hex string.

        Args:
            data: The string data to sign.

        Returns:
            Hex-encoded signature string with algorithm prefix.
            Format: "ecdsa-p256:<hex>" or "hmac-sha256:<hex>"
        """
        if not self._use_fallback and self._private_key:
            try:
                from cryptography.hazmat.primitives import hashes
                from cryptography.hazmat.primitives.asymmetric import ec
                signature = self._private_key.sign(
                    data.encode(),
                    ec.ECDSA(hashes.SHA256()),
                )
                return f"{self.ALGO_ECDSA}:{signature.hex()}"
            except Exception as exc:
                logger.error("ECDSASigner: ECDSA signing failed: %s", exc)

        # HMAC fallback — requires DEV MODE in production
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
        """Verify a signature against data.

        Supports both algorithm-prefixed signatures (ecdsa-p256:<hex>,
        hmac-sha256:<hex>) and legacy prefixless signatures for backward
        compatibility during migration.

        Args:
            data: The original string data.
            signature_hex: Hex-encoded signature to verify (optionally prefixed).

        Returns:
            True if the signature is valid.
        """
        # Parse algorithm prefix
        if ":" in signature_hex:
            algo, sig = signature_hex.split(":", 1)
        else:
            # Legacy: no prefix — try both algorithms for migration
            algo = None
            sig = signature_hex

        # ECDSA verification
        if algo == self.ALGO_ECDSA or (algo is None and not self._use_fallback):
            try:
                from cryptography.hazmat.primitives import hashes
                from cryptography.hazmat.primitives.asymmetric import ec
                signature = bytes.fromhex(sig)
                self._public_key.verify(
                    signature, data.encode(), ec.ECDSA(hashes.SHA256()),
                )
                return True
            except Exception:
                if algo == self.ALGO_ECDSA:
                    # ECDSA tag present — must verify as ECDSA only
                    return False
                # Legacy: fall through to HMAC attempt

        # HMAC verification
        if algo == self.ALGO_HMAC or algo is None:
            if self._fallback_key:
                expected = hmac.new(
                    self._fallback_key.encode(), data.encode(), hashlib.sha256,
                ).hexdigest()
                return hmac.compare_digest(expected, sig)

        return False

    def get_public_key_pem(self) -> str:
        """Get the public key in PEM format."""
        if self._public_key and not self._use_fallback:
            try:
                from cryptography.hazmat.primitives import serialization
                return self._public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                ).decode()
            except Exception:
                pass
        return ""

    def is_using_fallback(self) -> bool:
        """Check if using HMAC fallback instead of proper ECDSA."""
        return self._use_fallback

    def get_signature_algorithm(self) -> str:
        """Get the algorithm used for signing."""
        if not self._use_fallback and self._private_key:
            return self.ALGO_ECDSA
        return self.ALGO_HMAC


# ── Module-level helpers ──────────────────────────────────

_default_signer: Optional[ECDSASigner] = None


def get_signer() -> ECDSASigner:
    """Get or create the default ECDSA signer."""
    global _default_signer
    if _default_signer is None:
        _default_signer = ECDSASigner()
    return _default_signer


def sign_data(data: str) -> str:
    """Sign data using the default signer."""
    return get_signer().sign(data)


def verify_signature(data: str, signature: str) -> bool:
    """Verify a signature using the default signer."""
    return get_signer().verify(data, signature)
