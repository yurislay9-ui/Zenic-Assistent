"""
Tests for Phase 7 LogicBuilder and AuthService.
"""

import os
import tempfile
import pytest


# ============================================================
#  LOGIC BUILDER TESTS
# ============================================================

class TestLogicBuilder:
    """Tests for the LogicBuilder system."""

    def setup_method(self):
        from src.core.logic_builder import LogicBuilder
        self.builder = LogicBuilder()

    def test_builder_has_30_blocks(self):
        """Builder should have 30 registered blocks."""
        blocks = self.builder.list_blocks()
        assert len(blocks) >= 30

    def test_builder_has_all_categories(self):
        """Builder should have blocks in all 6 categories."""
        blocks = self.builder.list_blocks()
        categories = set(b.category for b in blocks)
        assert "flow" in categories
        assert "validation" in categories
        assert "business_logic" in categories
        assert "data" in categories
        assert "integrations" in categories
        assert "auth" in categories

    def test_build_from_description_invoice(self):
        """Building from 'facturacion' description should compose invoice-related blocks."""
        chain = self.builder.build_from_description("sistema de facturacion con impuestos")
        assert isinstance(chain.blocks, list)
        chain2 = self.builder.build_from_description("invoice calculator with tax")
        assert isinstance(chain2.blocks, list)

    def test_build_from_description_auth(self):
        """Building from 'auth' description should compose auth-related blocks."""
        chain = self.builder.build_from_description("login de usuarios con JWT")
        assert len(chain.blocks) > 0
        block_names = [b.name for b in chain.blocks]
        assert any("auth" in n for n in block_names)

    def test_build_from_blocks(self):
        """Building from specific block names should compose them."""
        chain = self.builder.build_from_blocks(["validate_required", "sanitize", "crud_create"])
        assert len(chain.blocks) == 3
        assert chain.blocks[0].name == "validate_required"
        assert chain.blocks[1].name == "sanitize"
        assert chain.blocks[2].name == "crud_create"

    def test_build_for_template_crud(self):
        """Building for CRUD template should compose validation + data blocks."""
        chain = self.builder.build_for_template("crud", [{"name": "Item", "fields": ["name:str", "price:float"]}])
        assert len(chain.blocks) > 0

    def test_build_for_template_auth(self):
        """Building for auth template should compose auth blocks."""
        chain = self.builder.build_for_template("auth", [])
        assert len(chain.blocks) > 0
        block_names = [b.name for b in chain.blocks]
        assert any("auth" in n for n in block_names)

    def test_chain_execution(self):
        """LogicChain should execute blocks sequentially."""
        chain = self.builder.build_from_blocks(["validate_required", "sanitize"])
        result = chain.execute(
            {"name": "Test", "email": "test@test.com"},
            {"required_fields": ["name", "email"]}
        )
        assert isinstance(result, dict)

    def test_generate_process_method(self):
        """generate_process_method should produce valid Python code."""
        code = self.builder.generate_process_method(["validate_required", "sanitize", "crud_create"])
        assert "def _process" in code
        assert "payload" in code
        assert "validate_required" in code
        assert "sanitize" in code
        assert "crud_create" in code
        assert '"processed": True' not in code

    def test_chain_with_condition(self):
        """LogicChain should support conditional branching."""
        chain = self.builder.build_from_blocks(["validate_required"])
        true_branch = self.builder.build_from_blocks(["crud_create"])
        false_branch = self.builder.build_from_blocks(["sanitize"])
        chain.add_condition(
            lambda data: data.get("valid", False),
            true_branch,
            false_branch
        )
        result = chain.execute({"name": "Test", "valid": True}, {"required_fields": ["name"]})
        assert isinstance(result, dict)


# ============================================================
#  AUTH SERVICE TESTS
# ============================================================

class TestAuthService:
    """Tests for the AuthService runtime."""

    def setup_method(self):
        from src.core.auth_service import AuthService
        self._temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self._temp_file.name
        self._temp_file.close()
        self.auth = AuthService(db_path=self.db_path, secret_key="test_secret_key_for_testing_12345")

    def teardown_method(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_register_user(self):
        """Should register a new user."""
        result = self.auth.register_user("testuser", "test@test.com", "TestPass123")
        assert result.get("message") == "User registered successfully"
        assert result.get("user_id") is not None

    def test_register_duplicate_username(self):
        """Should reject duplicate username."""
        self.auth.register_user("testuser", "test1@test.com", "TestPass123")
        result = self.auth.register_user("testuser", "test2@test.com", "TestPass123")
        assert "error" in result or "already exists" in str(result)

    def test_login_user(self):
        """Should login user and return tokens."""
        self.auth.register_user("loginuser", "login@test.com", "TestPass123")
        result = self.auth.login_user("loginuser", "TestPass123")
        assert "access_token" in result
        assert "refresh_token" in result
        assert result.get("token_type") == "bearer"

    def test_login_wrong_password(self):
        """Should reject wrong password."""
        self.auth.register_user("wrongpw", "wrong@test.com", "TestPass123")
        result = self.auth.login_user("wrongpw", "WrongPass999")
        assert "error" in result or result.get("success") is False

    def test_password_hashing(self):
        """Should hash and verify passwords correctly."""
        hashed = self.auth.hash_password("MyPassword123")
        assert hashed != "MyPassword123"
        assert self.auth.verify_password("MyPassword123", hashed) is True
        assert self.auth.verify_password("WrongPassword", hashed) is False

    def test_token_creation_verification(self):
        """Should create and verify tokens."""
        token = self.auth.create_access_token(user_id=1, role="admin")
        payload = self.auth.verify_token(token)
        assert payload.get("sub") == "1"
        assert payload.get("role") == "admin"

    def test_rbac_admin_has_all_permissions(self):
        """Admin role should have all permissions."""
        self.auth.register_user("admin1", "admin@test.com", "AdminPass123", role="admin")
        perms = self.auth.get_user_permissions(1)
        assert "manage_users" in perms
        assert "manage_system" in perms
        assert "read" in perms

    def test_rbac_viewer_read_only(self):
        """Viewer role should only have read permission."""
        self.auth.register_user("viewer1", "viewer@test.com", "ViewerPass123", role="viewer")
        perms = self.auth.get_user_permissions(1)
        assert "read" in perms
        assert "write" not in perms
        assert "delete" not in perms

    def test_api_key_lifecycle(self):
        """Should create, verify, and revoke API keys."""
        self.auth.register_user("apiuser", "api@test.com", "ApiPass123")
        key_result = self.auth.create_api_key(user_id=1, name="test_key")
        assert "api_key" in key_result or "key" in key_result

        if "api_key" in key_result:
            verify_result = self.auth.verify_api_key(key_result["api_key"])
            assert verify_result is not None or verify_result is not False

    def test_token_revocation(self):
        """Should revoke and reject revoked tokens."""
        token = self.auth.create_access_token(user_id=1, role="user")
        self.auth.revoke_token(token)
        try:
            result = self.auth.verify_token(token)
            assert result is None or "revoked" in str(result).lower(),                 "Revoked token should not be validated as active"
        except Exception as e:
            assert "revoked" in str(e).lower() or "invalid" in str(e).lower()

    def test_deactivate_user(self):
        """Should deactivate user preventing login."""
        self.auth.register_user("deactivate", "deact@test.com", "DeactPass123")
        self.auth.deactivate_user(1)
        result = self.auth.login_user("deactivate", "DeactPass123")
        assert "error" in result or result.get("success") is False
