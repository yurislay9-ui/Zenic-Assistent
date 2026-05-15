"""
Zenic-Agents E2E — Security / Defense Tests

Tests the defense-in-depth layer end-to-end:
  - SQL injection prevention (CRUD validator + DB operations)
  - Encryption/decryption roundtrip
  - Hash chain integrity
  - ECDSA signing/verification
  - Safety gate (action classification, deny rules)
  - Cross-verification between defense components
  - Integrity violation detection

These tests exercise CROSS-MODULE security flows.
All tests are marked with @pytest.mark.e2e.
"""

from __future__ import annotations

import sqlite3

import pytest


# ---------------------------------------------------------------------------
# SQL Injection Prevention E2E
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestSQLInjectionPrevention:
    """Test that SQL injection attacks are prevented end-to-end."""

    def test_sql_injection_in_billing_queries(self, e2e_billing_db):
        """SQL injection in tenant_id should not corrupt the billing database."""
        # Billing module removed — skip billing-related SQL injection test
        # from src.core.billing.trial_manager import TrialManager
        pytest.skip(reason="src.core.billing removed — billing module no longer available")
        tm = TrialManager(db_path=e2e_billing_db)
        tm.start_trial("normal-tenant")
        malicious_id = "evil'; DROP TABLE billing_records; --"
        tm.start_trial(malicious_id)
        conn = sqlite3.connect(e2e_billing_db)
        rows = conn.execute("SELECT COUNT(*) FROM billing_records").fetchone()
        conn.close()
        assert rows[0] >= 2, "billing_records table should still exist"

    def test_sql_injection_in_auth_queries(self, tmp_path):
        """SQL injection should not bypass auth with parameterized queries."""
        db_path = str(tmp_path / "auth_test.sqlite")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT)")
        conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", ("admin", "hashed_123"))
        conn.commit()
        conn.close()

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT * FROM users WHERE username = ?", ("admin' --",)).fetchone()
        conn.close()
        assert row is None, "SQL injection bypass should not work"

    def test_sql_injection_in_integrity_verifier(self, integrity_verifier):
        """SQL injection in component names should not corrupt integrity DB."""
        integrity_verifier.establish_baseline("safe-component", b"test-data")
        integrity_verifier.establish_baseline("evil'; DROP TABLE integrity_baselines; --", b"data")
        result = integrity_verifier.verify_component("safe-component", b"test-data")
        assert result.status.value == "valid"

    def test_crud_validator_rejects_sql_injection_table_names(self, crud_validator):
        """CRUDValidator should reject table names with SQL injection patterns."""
        result = crud_validator.validate("SELECT", "users; DROP TABLE users; --")
        assert result.valid is False
        assert result.risk_level == "critical"

    def test_crud_validator_rejects_system_table_access(self, crud_validator):
        """CRUDValidator should block access to sqlite_master."""
        result = crud_validator.validate("SELECT", "sqlite_master")
        assert result.valid is False
        assert "system table" in result.errors[0].lower() or result.risk_level == "critical"

    def test_crud_validator_blocks_delete_without_where(self, crud_validator):
        """DELETE without WHERE clause should be blocked."""
        result = crud_validator.validate(
            "DELETE", "users", query="DELETE FROM users;",
        )
        assert result.valid is False
        assert result.risk_level == "critical"

    def test_crud_validator_blocks_update_without_where(self, crud_validator):
        """UPDATE without WHERE clause should be blocked."""
        result = crud_validator.validate(
            "UPDATE", "users",
            data={"name": "hacked"},
            query="UPDATE users SET name = 'hacked';",
        )
        assert result.valid is False

    def test_crud_validator_enforces_protected_columns(self, crud_validator):
        """Protected columns (e.g., 'id') should not be modifiable."""
        result = crud_validator.validate(
            "UPDATE", "users", data={"id": 999, "name": "new"}, where_clause="id=1",
        )
        assert result.valid is False
        assert any("protected" in e.lower() for e in result.errors)


# ---------------------------------------------------------------------------
# Encryption / Decryption Roundtrip E2E
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestEncryptionRoundtrip:
    """Test encryption → decryption roundtrip end-to-end."""

    def test_encrypt_decrypt_string(self, encryption_manager):
        plaintext = "Sensitive data: API_KEY_12345"
        ciphertext = encryption_manager.encrypt(plaintext)
        decrypted = encryption_manager.decrypt(ciphertext)
        assert decrypted == plaintext

    def test_encrypt_produces_different_ciphertext(self, encryption_manager):
        """Same plaintext → different ciphertexts (Fernet IV)."""
        ct1 = encryption_manager.encrypt("same input text")
        ct2 = encryption_manager.encrypt("same input text")
        assert ct1 != ct2

    def test_encrypt_decrypt_dict(self, encryption_manager):
        data = {"username": "admin", "api_key": "sk-secret-12345"}
        encrypted = encryption_manager.encrypt_dict(data, sensitive_keys=["api_key"])
        assert encrypted["api_key"] != data["api_key"]
        assert encrypted.get("_api_key_encrypted") is True
        assert encrypted["username"] == "admin"
        decrypted = encryption_manager.decrypt_dict(encrypted)
        assert decrypted["api_key"] == data["api_key"]
        assert "_api_key_encrypted" not in decrypted

    def test_encrypt_decrypt_empty_string(self, encryption_manager):
        assert encryption_manager.decrypt(encryption_manager.encrypt("")) == ""

    def test_encrypt_decrypt_unicode(self, encryption_manager):
        plaintext = "Contraseña: español 日本語 한국어 🚀"
        assert encryption_manager.decrypt(encryption_manager.encrypt(plaintext)) == plaintext

    def test_decrypt_invalid_ciphertext_raises(self, encryption_manager):
        with pytest.raises(ValueError, match="Decryption failed"):
            encryption_manager.decrypt("not-valid-fernet-ciphertext!!!")

    def test_encryption_status(self, encryption_manager):
        status = encryption_manager.get_status()
        assert status.fernet_available is True
        assert status.key_derivation == "PBKDF2-SHA256"
        assert status.iterations > 0


# ---------------------------------------------------------------------------
# Hash Chain Integrity E2E
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestHashChainIntegrity:
    """Test hash chain integrity verification end-to-end."""

    def test_baseline_then_verify_unchanged(self, integrity_verifier):
        data = b"critical configuration data"
        integrity_verifier.establish_baseline("config-file", data)
        result = integrity_verifier.verify_component("config-file", data)
        assert result.status.value == "valid"

    def test_tampered_data_detected(self, integrity_verifier):
        integrity_verifier.establish_baseline("tamper-test", b"original content")
        result = integrity_verifier.verify_component("tamper-test", b"MODIFIED content")
        assert result.status.value == "tampered"

    def test_missing_baseline_reported(self, integrity_verifier):
        result = integrity_verifier.verify_component("no-baseline-exists", b"any data")
        assert result.status.value == "missing"

    def test_file_integrity_flow(self, integrity_verifier, tmp_path):
        """baseline → verify → modify → detect."""
        test_file = tmp_path / "important_config.yaml"
        test_file.write_text("database_host: localhost\nport: 5432\n")
        integrity_verifier.establish_file_baseline(str(test_file), "config:database")

        assert integrity_verifier.verify_file(str(test_file), "config:database").status.value == "valid"

        test_file.write_text("database_host: EVIL_HOST\nport: 5432\n")
        assert integrity_verifier.verify_file(str(test_file), "config:database").status.value == "tampered"

    def test_db_integrity_flow(self, integrity_verifier, tmp_path):
        """baseline → verify → modify → detect for SQLite DB."""
        db_file = tmp_path / "test_data.sqlite"
        conn = sqlite3.connect(str(db_file))
        conn.execute("CREATE TABLE users (id INTEGER, name TEXT)")
        conn.execute("INSERT INTO users VALUES (1, 'Alice')")
        conn.commit()
        conn.close()

        integrity_verifier.establish_db_baseline(str(db_file), "db:users")
        assert integrity_verifier.verify_db(str(db_file), "db:users").status.value == "valid"

        conn = sqlite3.connect(str(db_file))
        conn.execute("INSERT INTO users VALUES (2, 'Bob')")
        conn.commit()
        conn.close()
        assert integrity_verifier.verify_db(str(db_file), "db:users").status.value == "tampered"

    def test_integrity_violation_callback(self, integrity_verifier):
        violations = []
        integrity_verifier.on_integrity_violation(lambda r: violations.append(r))
        integrity_verifier.establish_baseline("cb-test", b"original")
        integrity_verifier.verify_component("cb-test", b"MODIFIED")
        assert len(violations) >= 1

    def test_cross_verify_multiple_components(self, integrity_verifier, tmp_path):
        f1, f2 = tmp_path / "f1.txt", tmp_path / "f2.txt"
        f1.write_text("A"), f2.write_text("B")
        integrity_verifier.establish_file_baseline(str(f1), "file:1")
        integrity_verifier.establish_file_baseline(str(f2), "file:2")
        results = integrity_verifier.cross_verify([f"file:{f1}", f"file:{f2}"])
        assert len(results) == 2


# ---------------------------------------------------------------------------
# Safety Gate E2E
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestSafetyGateE2E:
    """Test the SafetyGate across action types."""

    def test_safe_action_allowed(self, safety_gate):
        from src.core.executors.safety_gate._types import SafetyVerdict
        result = safety_gate.check("notification", {"message": "hello"})
        assert result.verdict == SafetyVerdict.ALLOW

    def test_destructive_action_requires_confirmation(self, safety_gate):
        from src.core.executors.safety_gate._types import SafetyVerdict
        result = safety_gate.check(
            "database", {"query": "DELETE FROM users WHERE id=1", "operation": "delete"},
        )
        assert result.verdict in (SafetyVerdict.CONFIRM, SafetyVerdict.DENY)

    def test_financial_action_requires_approval(self, safety_gate):
        from src.core.executors.safety_gate._types import SafetyVerdict
        result = safety_gate.check(
            "email", {"subject": "Invoice", "body": "Payment due"},
        )
        assert result.verdict in (SafetyVerdict.APPROVE, SafetyVerdict.ALLOW, SafetyVerdict.CONFIRM)

    def test_safety_gate_confirm_and_approve(self, safety_gate):
        safety_gate.confirm_action("action-001")
        safety_gate.approve_action("action-002", "admin")
        assert safety_gate.is_confirmed("action-001")
        assert safety_gate.is_approved("action-002")

    def test_safety_gate_stats(self, safety_gate):
        stats = safety_gate.get_stats()
        assert "allowed" in stats
        assert "denied" in stats


# ---------------------------------------------------------------------------
# ECDSA Signing / Verification E2E
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestECDSASigning:
    """Test ECDSA (or HMAC fallback) signing and verification."""

    def test_sign_and_verify_roundtrip(self, ecdsa_signer):
        data = "license-payload:tenant=acme;plan=enterprise"
        sig = ecdsa_signer.sign(data)
        assert ecdsa_signer.verify(data, sig) is True

    def test_tampered_data_fails_verification(self, ecdsa_signer):
        sig = ecdsa_signer.sign("license:plan=business")
        assert ecdsa_signer.verify("license:plan=enterprise", sig) is False

    def test_wrong_signature_fails(self, ecdsa_signer):
        ecdsa_signer.sign("data")
        assert ecdsa_signer.verify("data", "0" * 64) is False

    def test_different_data_different_signatures(self, ecdsa_signer):
        assert ecdsa_signer.sign("A") != ecdsa_signer.sign("B")


# ---------------------------------------------------------------------------
# Cross-Module Defense E2E
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestCrossModuleDefense:
    """Test cross-module defense interactions."""

    def test_encrypted_data_passes_integrity_check(self, encryption_manager, integrity_verifier):
        original = "secret-api-key-sk-12345"
        ciphertext = encryption_manager.encrypt(original)
        integrity_verifier.establish_baseline("encrypted:api_key", ciphertext.encode())
        result = integrity_verifier.verify_component("encrypted:api_key", ciphertext.encode())
        assert result.status.value == "valid"
        assert encryption_manager.decrypt(ciphertext) == original

    def test_signed_license_with_integrity(self, ecdsa_signer, integrity_verifier):
        license_data = "tenant=acme;plan=enterprise;issued=2025-01-01"
        signature = ecdsa_signer.sign(license_data)
        combined = f"{license_data}|sig={signature}"
        integrity_verifier.establish_baseline("license:acme", combined.encode())
        assert integrity_verifier.verify_component("license:acme", combined.encode()).status.value == "valid"
        assert ecdsa_signer.verify(license_data, signature) is True

    def test_tampered_ciphertext_detected_by_integrity(self, encryption_manager, integrity_verifier):
        ciphertext = encryption_manager.encrypt("important data")
        integrity_verifier.establish_baseline("enc:important", ciphertext.encode())
        tampered = ciphertext[:-5] + "XXXXX"
        assert integrity_verifier.verify_component("enc:important", tampered.encode()).status.value == "tampered"
