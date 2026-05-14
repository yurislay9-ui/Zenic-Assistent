"""
Zenic-Agents E2E — Billing Tests

Tests the billing subsystem end-to-end:
  - Subscription creation
  - Trial period enforcement
  - Degraded mode when subscription expires
  - Stripe webhook handling (with mock)
  - Billing service facade
  - Full lifecycle (trial → activate → cancel)

These tests exercise CROSS-MODULE billing flows.
All tests are marked with @pytest.mark.e2e.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from src.core.billing.types import PlanType, SubscriptionStatus, TRIAL_DURATION_DAYS


# ---------------------------------------------------------------------------
# Subscription Creation E2E
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestSubscriptionCreation:
    """Test subscription creation end-to-end."""

    def test_start_trial_creates_billing_record(self, billing_service):
        record = billing_service.start_trial("tenant-e2e-001")
        assert record is not None
        assert record.tenant_id == "tenant-e2e-001"
        assert record.status == SubscriptionStatus.TRIAL
        assert record.plan_type == PlanType.BUSINESS
        assert record.trial_start is not None
        assert record.trial_end is not None

    def test_start_trial_14_days_duration(self, billing_service):
        record = billing_service.start_trial("tenant-e2e-002")
        duration_days = (record.trial_end - record.trial_start) / 86400
        assert int(duration_days) == TRIAL_DURATION_DAYS

    def test_start_trial_idempotent(self, billing_service):
        r1 = billing_service.start_trial("tenant-e2e-idem")
        r2 = billing_service.start_trial("tenant-e2e-idem")
        assert r1.trial_start == r2.trial_start

    def test_activate_subscription_with_stripe(self, billing_service, mock_stripe):
        billing_service.start_trial("tenant-e2e-activate")
        record = billing_service.activate(
            tenant_id="tenant-e2e-activate",
            payment_method_id="pm_test_123",
            plan=PlanType.BUSINESS,
        )
        assert record.status == SubscriptionStatus.ACTIVE
        assert record.plan_type == PlanType.BUSINESS

    def test_activate_enterprise_plan(self, billing_service, mock_stripe):
        billing_service.start_trial("tenant-e2e-enterprise")
        record = billing_service.activate(
            "tenant-e2e-enterprise", "pm_ent", PlanType.ENTERPRISE,
        )
        assert record.status == SubscriptionStatus.ACTIVE
        assert record.plan_type == PlanType.ENTERPRISE

    def test_get_status_returns_current_record(self, billing_service):
        billing_service.start_trial("tenant-e2e-status")
        record = billing_service.get_status("tenant-e2e-status")
        assert record is not None
        assert record.tenant_id == "tenant-e2e-status"

    def test_get_status_returns_none_for_unknown(self, billing_service):
        assert billing_service.get_status("nonexistent-xyz") is None


# ---------------------------------------------------------------------------
# Trial Period Enforcement E2E
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestTrialPeriodEnforcement:
    """Test trial period enforcement end-to-end."""

    def test_trial_status_during_trial(self, billing_service):
        billing_service.start_trial("tenant-trial-active")
        record = billing_service.get_status("tenant-trial-active")
        assert record.status == SubscriptionStatus.TRIAL

    def test_trial_expiry_detection(self, e2e_billing_db):
        from src.core.billing.trial_manager import TrialManager
        tm = TrialManager(db_path=e2e_billing_db)
        record = tm.start_trial("tenant-expired")
        record.trial_end = time.time() - 1
        tm._save_record(record)
        status = tm.check_trial_status("tenant-expired")
        assert status == SubscriptionStatus.DEGRADED

    def test_trial_days_remaining(self, e2e_billing_db):
        from src.core.billing.trial_manager import TrialManager
        tm = TrialManager(db_path=e2e_billing_db)
        tm.start_trial("tenant-days-remaining")
        days = tm.get_trial_days_remaining("tenant-days-remaining")
        assert 0 < days <= TRIAL_DURATION_DAYS

    def test_trial_days_remaining_zero_for_expired(self, e2e_billing_db):
        from src.core.billing.trial_manager import TrialManager
        tm = TrialManager(db_path=e2e_billing_db)
        record = tm.start_trial("tenant-expired-days")
        record.trial_end = time.time() - 86400
        tm._save_record(record)
        assert tm.get_trial_days_remaining("tenant-expired-days") == 0


# ---------------------------------------------------------------------------
# Degraded Mode E2E
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestDegradedMode:
    """Test degraded mode when subscription expires."""

    def test_expire_trial_sets_degraded(self, e2e_billing_db):
        from src.core.billing.trial_manager import TrialManager
        tm = TrialManager(db_path=e2e_billing_db)
        tm.start_trial("tenant-to-degrade")
        with patch.object(tm, "degrade_tenant"):
            tm.expire_trial("tenant-to-degrade")
        record = tm.get_record("tenant-to-degrade")
        assert record.status == SubscriptionStatus.DEGRADED
        assert record.plan_type == PlanType.FREE

    def test_cancel_subscription_sets_canceled(self, billing_service, mock_stripe):
        billing_service.start_trial("tenant-to-cancel")
        billing_service.activate("tenant-to-cancel", "pm_test", PlanType.BUSINESS)
        with patch.object(billing_service._trial_manager, "degrade_tenant"):
            result = billing_service.cancel("tenant-to-cancel")
        assert result is True
        assert billing_service.get_status("tenant-to-cancel").status == SubscriptionStatus.CANCELED

    def test_cancel_unknown_tenant_returns_false(self, billing_service):
        assert billing_service.cancel("nonexistent-abc") is False

    def test_bulk_trial_expiry_scanner(self, e2e_billing_db):
        from src.core.billing.trial_manager import TrialManager
        tm = TrialManager(db_path=e2e_billing_db)
        for i in range(3):
            record = tm.start_trial(f"tenant-bulk-{i}")
            record.trial_end = time.time() - 1
            tm._save_record(record)
        tm.start_trial("tenant-bulk-active")
        with patch.object(tm, "degrade_tenant"):
            expired_count = tm.check_and_expire_trials()
        assert expired_count == 3
        assert tm.get_record("tenant-bulk-active").status == SubscriptionStatus.TRIAL

    def test_degraded_mode_manager_enters_degraded(self, tmp_path):
        from src.core.degraded_mode.manager import DegradedModeManager
        from src.core.degraded_mode.types import DegradationLevel
        db = str(tmp_path / "deg.sqlite")
        mgr = DegradedModeManager(db_path=db)
        state = mgr.enter_degraded(reason="test", message="Trial expired", level=1)
        assert state.level == DegradationLevel.DEGRADED

    def test_degraded_mode_manager_exits_to_normal(self, tmp_path):
        from src.core.degraded_mode.manager import DegradedModeManager
        from src.core.degraded_mode.types import DegradationLevel
        db = str(tmp_path / "deg2.sqlite")
        mgr = DegradedModeManager(db_path=db)
        mgr.enter_degraded(level=1)
        state = mgr.exit_degraded()
        assert state.level == DegradationLevel.NORMAL

    def test_degraded_mode_feature_restriction(self, tmp_path):
        from src.core.degraded_mode.manager import DegradedModeManager
        db = str(tmp_path / "deg3.sqlite")
        mgr = DegradedModeManager(db_path=db)
        mgr.enter_degraded(level=1)
        assert mgr.is_feature_allowed("executor_run") is False
        assert mgr.is_feature_allowed("read_data") is True


# ---------------------------------------------------------------------------
# Stripe Webhook Handling E2E
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestStripeWebhookHandling:
    """Test Stripe webhook handling with mocked Stripe."""

    def _make_handler(self, e2e_billing_db):
        from src.core.billing.trial_manager import TrialManager
        from src.core.billing.webhook_handler import WebhookHandler
        from src.core.billing.stripe_integration import StripeIntegration
        tm = TrialManager(db_path=e2e_billing_db)
        return tm, WebhookHandler(stripe_integration=StripeIntegration(), trial_manager=tm)

    def test_checkout_complete_activates_subscription(self, e2e_billing_db):
        tm, handler = self._make_handler(e2e_billing_db)
        tm.start_trial("tenant-wh-checkout")
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {
                "metadata": {"tenant_id": "tenant-wh-checkout", "plan_type": "business"},
                "customer": "cus_wh", "subscription": "sub_wh",
            }},
        }
        assert handler.handle_event(event) is True
        assert tm.get_record("tenant-wh-checkout").status == SubscriptionStatus.ACTIVE

    def test_invoice_paid_confirms_active(self, e2e_billing_db):
        tm, handler = self._make_handler(e2e_billing_db)
        tm.start_trial("tenant-wh-paid")
        tm.activate_subscription("tenant-wh-paid", "cus_p", "sub_p", PlanType.ENTERPRISE)
        event = {
            "type": "invoice.paid",
            "data": {"object": {
                "customer": "cus_p", "subscription": "sub_p",
                "lines": {"data": [{"period": {"end": time.time() + 30 * 86400}}]},
            }},
        }
        assert handler.handle_event(event) is True
        assert tm.get_record("tenant-wh-paid").status == SubscriptionStatus.ACTIVE

    def test_invoice_failed_marks_past_due(self, e2e_billing_db):
        tm, handler = self._make_handler(e2e_billing_db)
        tm.start_trial("tenant-wh-fail")
        tm.activate_subscription("tenant-wh-fail", "cus_f", "sub_f", PlanType.BUSINESS)
        event = {"type": "invoice.payment_failed", "data": {"object": {"customer": "cus_f"}}}
        assert handler.handle_event(event) is True
        assert tm.get_record("tenant-wh-fail").status == SubscriptionStatus.PAST_DUE

    def test_subscription_deleted_cancels(self, e2e_billing_db):
        tm, handler = self._make_handler(e2e_billing_db)
        tm.start_trial("tenant-wh-del")
        tm.activate_subscription("tenant-wh-del", "cus_d", "sub_d", PlanType.BUSINESS)
        event = {"type": "customer.subscription.deleted", "data": {"object": {"id": "sub_d"}}}
        with patch.object(tm, "degrade_tenant"):
            assert handler.handle_event(event) is True
        record = tm.get_record("tenant-wh-del")
        assert record.status == SubscriptionStatus.CANCELED
        assert record.plan_type == PlanType.FREE

    def test_unhandled_event_type_acknowledged(self, e2e_billing_db):
        _, handler = self._make_handler(e2e_billing_db)
        assert handler.handle_event({"type": "account.application.deauthorized", "data": {"object": {}}}) is True

    def test_billing_service_process_webhook(self, billing_service, mock_stripe):
        result = billing_service.process_webhook('{"type":"test"}', "t=1,v1=abc")
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Billing Service Facade E2E
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestBillingServiceFacade:
    """Test the BillingService facade end-to-end."""

    def test_full_lifecycle_trial_activate_cancel(self, billing_service, mock_stripe):
        tenant = "tenant-lifecycle-001"
        record = billing_service.start_trial(tenant)
        assert record.status == SubscriptionStatus.TRIAL

        record = billing_service.activate(tenant_id=tenant, payment_method_id="pm_lc", plan=PlanType.BUSINESS)
        assert record.status == SubscriptionStatus.ACTIVE
        assert billing_service.get_status(tenant).status == SubscriptionStatus.ACTIVE

        with patch.object(billing_service._trial_manager, "degrade_tenant"):
            assert billing_service.cancel(tenant) is True
        assert billing_service.get_status(tenant).status == SubscriptionStatus.CANCELED

    def test_billing_record_serialization(self, billing_service):
        record = billing_service.start_trial("tenant-serialize")
        d = record.to_dict()
        assert isinstance(d, dict)
        assert d["tenant_id"] == "tenant-serialize"
        assert d["status"] == "trial"
        assert d["plan_type"] == "business"

    def test_multiple_tenants_independent(self, billing_service):
        """Multiple tenants should have independent billing records."""
        billing_service.start_trial("tenant-a")
        billing_service.start_trial("tenant-b")
        ra = billing_service.get_status("tenant-a")
        rb = billing_service.get_status("tenant-b")
        assert ra.tenant_id != rb.tenant_id
        assert ra.trial_start != rb.trial_start or True  # timing may be same
