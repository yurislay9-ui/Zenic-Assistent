"""
Zenic-Agents Asistente - Blueprint Certifier (Phase 5)

ECDSA cryptographic certification for Blueprints.
Provides:
  - Key pair generation (secp256r1 / P-256)
  - Blueprint signing with ECDSA
  - Signature verification
  - Certificate management

Falls back to HMAC-SHA256 if cryptography library is not available,
providing integrity checking without full PKI.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

from .types import BlueprintSignature, BlueprintStatus

logger = logging.getLogger(__name__)

# Try to import cryptography for ECDSA
try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, utils
    from cryptography.hazmat.primitives.asymmetric.ec import (
        EllipticCurvePrivateKey, EllipticCurvePublicKey,
    )
    from cryptography.exceptions import InvalidSignature
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False
    logger.debug("certifier: 'cryptography' not available, using HMAC fallback")


# ──────────────────────────────────────────────────────────────
#  KEY MANAGEMENT
# ──────────────────────────────────────────────────────────────

class CertifierKeyPair:
    """Manages ECDSA key pair for Blueprint certification.

    When cryptography library is available, uses ECDSA P-256.
    Otherwise, falls back to HMAC-SHA256 with a shared secret.
    """

    def __init__(self, private_key_pem: str = "", public_key_pem: str = "") -> None:
        self._private_key: Any = None
        self._public_key: Any = None
        self._hmac_secret: bytes = b""
        self._public_key_hex: str = ""
        self._signer_id: str = ""

        if _HAS_CRYPTO:
            if private_key_pem:
                self._load_private_key(private_key_pem)
            elif public_key_pem:
                self._load_public_key(public_key_pem)
            else:
                self._generate_key_pair()
        else:
            # HMAC fallback
            self._hmac_secret = os.urandom(32)
            self._public_key_hex = hashlib.sha256(
                self._hmac_secret
            ).hexdigest()

    def _generate_key_pair(self) -> None:
        """Generate a new ECDSA P-256 key pair."""
        if not _HAS_CRYPTO:
            return
        self._private_key = ec.generate_private_key(ec.SECP256R1())
        self._public_key = self._private_key.public_key()
        pub_bytes = self._public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        self._public_key_hex = pub_bytes.hex()

    def _load_private_key(self, pem: str) -> None:
        """Load a private key from PEM."""
        if not _HAS_CRYPTO:
            return
        self._private_key = serialization.load_pem_private_key(
            pem.encode(), password=None,
        )
        self._public_key = self._private_key.public_key()
        pub_bytes = self._public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        self._public_key_hex = pub_bytes.hex()

    def _load_public_key(self, pem: str) -> None:
        """Load a public key from PEM (verification only)."""
        if not _HAS_CRYPTO:
            return
        self._public_key = serialization.load_pem_public_key(
            pem.encode(),
        )
        pub_bytes = self._public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        self._public_key_hex = pub_bytes.hex()

    @property
    def can_sign(self) -> bool:
        """Check if this key pair can sign (has private key)."""
        if _HAS_CRYPTO:
            return self._private_key is not None
        return bool(self._hmac_secret)

    @property
    def public_key_hex(self) -> str:
        """Get the public key as hex string."""
        return self._public_key_hex

    @property
    def public_key_pem(self) -> str:
        """Get the public key as PEM string."""
        if not _HAS_CRYPTO or self._public_key is None:
            return ""
        return self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

    @property
    def private_key_pem(self) -> str:
        """Get the private key as PEM string."""
        if not _HAS_CRYPTO or self._private_key is None:
            return ""
        return self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")


# ──────────────────────────────────────────────────────────────
#  CERTIFIER
# ──────────────────────────────────────────────────────────────

class BlueprintCertifier:
    """Signs and verifies Blueprint certificates using ECDSA.

    Usage:
        certifier = BlueprintCertifier()
        signature = certifier.sign(blueprint)
        is_valid = certifier.verify(blueprint, signature)
    """

    def __init__(self, key_pair: Optional[CertifierKeyPair] = None) -> None:
        self._key_pair = key_pair or CertifierKeyPair()

    def sign(self, content_hash: str, signer_id: str = "") -> BlueprintSignature:
        """Sign a Blueprint's content hash.

        Args:
            content_hash: SHA-256 hash of Blueprint content.
            signer_id: Identifier of the signer.

        Returns:
            BlueprintSignature with the cryptographic signature.
        """
        if not self._key_pair.can_sign:
            raise RuntimeError("Certifier has no private key for signing")

        signature_hex = ""
        algorithm = "HMAC-SHA256"

        if _HAS_CRYPTO and self._key_pair._private_key is not None:
            # ECDSA signing
            algorithm = "ECDSA-P256"
            signature_bytes = self._key_pair._private_key.sign(
                content_hash.encode("utf-8"),
                ec.ECDSA(hashes.SHA256()),
            )
            signature_hex = signature_bytes.hex()
        else:
            # HMAC fallback
            sig = hmac.new(
                self._key_pair._hmac_secret,
                content_hash.encode("utf-8"),
                hashlib.sha256,
            )
            signature_hex = sig.hexdigest()

        return BlueprintSignature(
            algorithm=algorithm,
            signature_hex=signature_hex,
            public_key_hex=self._key_pair.public_key_hex,
            signed_at=time.time(),
            signer_id=signer_id or "zenic-agents",
        )

    def verify(
        self,
        content_hash: str,
        signature: BlueprintSignature,
    ) -> bool:
        """Verify a Blueprint's signature against its content hash.

        Args:
            content_hash: SHA-256 hash of Blueprint content.
            signature: The signature to verify.

        Returns:
            True if signature is valid, False otherwise.
        """
        if not signature.signature_hex:
            logger.warning("Certifier: Empty signature")
            return False

        if _HAS_CRYPTO and signature.algorithm == "ECDSA-P256":
            return self._verify_ecdsa(content_hash, signature)
        else:
            return self._verify_hmac(content_hash, signature)

    def _verify_ecdsa(
        self, content_hash: str, signature: BlueprintSignature,
    ) -> bool:
        """Verify an ECDSA signature."""
        if not _HAS_CRYPTO:
            logger.warning("Certifier: cryptography lib not available for ECDSA")
            return False

        try:
            # Reconstruct public key from hex
            pub_bytes = bytes.fromhex(signature.public_key_hex)
            public_key = EllipticCurvePublicKey.from_encoded_point(
                ec.SECP256R1(), pub_bytes,
            )
            sig_bytes = bytes.fromhex(signature.signature_hex)
            public_key.verify(
                sig_bytes,
                content_hash.encode("utf-8"),
                ec.ECDSA(hashes.SHA256()),
            )
            return True
        except (InvalidSignature, Exception) as e:
            logger.warning("Certifier: ECDSA verification failed: %s", e)
            return False

    def _verify_hmac(
        self, content_hash: str, signature: BlueprintSignature,
    ) -> bool:
        """Verify an HMAC signature (requires same secret)."""
        if not self._key_pair._hmac_secret:
            logger.warning("Certifier: No HMAC secret for verification")
            return False

        expected = hmac.new(
            self._key_pair._hmac_secret,
            content_hash.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature.signature_hex)

    @property
    def key_pair(self) -> CertifierKeyPair:
        """Get the current key pair."""
        return self._key_pair


# ──────────────────────────────────────────────────────────────
#  CONVENIENCE FUNCTIONS
# ──────────────────────────────────────────────────────────────

_default_certifier: Optional[BlueprintCertifier] = None


def get_default_certifier() -> BlueprintCertifier:
    """Get or create the default BlueprintCertifier."""
    global _default_certifier
    if _default_certifier is None:
        _default_certifier = BlueprintCertifier()
    return _default_certifier


def certify_blueprint(blueprint: "CertifiedBlueprint") -> BlueprintSignature:
    """Certify a Blueprint with the default certifier.

    Signs the Blueprint's content hash and updates its metadata.
    """
    from .schema import CertifiedBlueprint  # Avoid circular import
    certifier = get_default_certifier()
    content_hash = blueprint.content_hash()
    signature = certifier.sign(content_hash)
    blueprint.metadata.signature = signature
    blueprint.metadata.status = BlueprintStatus.CERTIFIED
    return signature


def verify_blueprint(blueprint: "CertifiedBlueprint") -> bool:
    """Verify a Blueprint's certification signature."""
    if not blueprint.metadata.signature:
        return False
    certifier = get_default_certifier()
    content_hash = blueprint.content_hash()
    return certifier.verify(content_hash, blueprint.metadata.signature)
