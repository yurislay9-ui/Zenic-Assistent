"""
Zenic-Agents Asistente - Blueprint Onboarding System (Phase 5)

Guided onboarding flow for Blueprint selection and configuration.
Steps:
  1. SELECT_BLUEPRINT — User selects domain Blueprints
  2. IMPORT_DATA — Import existing documents/data
  3. CONFIGURE_MONITORS — Configure SNA monitor thresholds
  4. CONFIGURE_NOTIFICATIONS — Set up notification channels
  5. REVIEW — Review all configurations
  6. COMPLETE — Apply and activate
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional

from .types import (
    BlueprintTier, MonitorHook,
    OnboardingSession, OnboardingStep, OnboardingStepType,
)
from .schema import CertifiedBlueprint
from .composer import BlueprintComposer, CompositionResult
from .loader import BlueprintLoaderV2
from .converter import NicheConverter

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  STEP BUILDER
# ──────────────────────────────────────────────────────────────

def build_default_steps() -> List[OnboardingStep]:
    """Build the default onboarding step sequence."""
    return [
        OnboardingStep(
            step_type=OnboardingStepType.SELECT_BLUEPRINT,
            title="Select Blueprints",
            description="Choose the domain Blueprints for your setup",
            required=True,
        ),
        OnboardingStep(
            step_type=OnboardingStepType.IMPORT_DATA,
            title="Import Data",
            description="Import existing documents, inventories, or data files",
            required=False,
        ),
        OnboardingStep(
            step_type=OnboardingStepType.CONFIGURE_MONITORS,
            title="Configure Monitors",
            description="Set up monitoring thresholds and alert preferences",
            required=True,
        ),
        OnboardingStep(
            step_type=OnboardingStepType.CONFIGURE_NOTIFICATIONS,
            title="Configure Notifications",
            description="Set up notification channels (Telegram, email, etc.)",
            required=True,
        ),
        OnboardingStep(
            step_type=OnboardingStepType.REVIEW,
            title="Review Configuration",
            description="Review all settings before activation",
            required=True,
        ),
        OnboardingStep(
            step_type=OnboardingStepType.COMPLETE,
            title="Complete Setup",
            description="Activate your configured Blueprint",
            required=True,
        ),
    ]


# ──────────────────────────────────────────────────────────────
#  ONBOARDING ENGINE
# ──────────────────────────────────────────────────────────────

class OnboardingEngine:
    """Guides users through Blueprint selection and configuration.

    Usage:
        engine = OnboardingEngine()
        session = engine.start_session(tenant_id="acme", user_id="admin")
        available = engine.list_available_blueprints()
        engine.select_blueprints(session, ["retail_inventory", "billing"])
        result = engine.complete_onboarding(session)
    """

    def __init__(
        self,
        loader: Optional[BlueprintLoaderV2] = None,
        composer: Optional[BlueprintComposer] = None,
    ) -> None:
        self._loader = loader or BlueprintLoaderV2()
        self._composer = composer or BlueprintComposer()
        self._available_blueprints: Dict[str, CertifiedBlueprint] = {}
        self._sessions: Dict[str, OnboardingSession] = {}
        self._hooks: Dict[str, List[Callable]] = {}

    # ── Session Management ─────────────────────────────────

    def start_session(
        self, tenant_id: str = "", user_id: str = "",
    ) -> OnboardingSession:
        """Start a new onboarding session."""
        session = OnboardingSession(
            tenant_id=tenant_id, user_id=user_id,
            steps=build_default_steps(),
        )
        self._sessions[session.session_id] = session
        logger.info(
            "OnboardingEngine: Started session %s for tenant=%s",
            session.session_id, tenant_id,
        )
        return session

    def get_session(self, session_id: str) -> Optional[OnboardingSession]:
        """Get an existing onboarding session."""
        return self._sessions.get(session_id)

    def cancel_session(self, session_id: str) -> bool:
        """Cancel an onboarding session."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    # ── Blueprint Selection ────────────────────────────────

    def load_available_blueprints(
        self, blueprints_dir: str = "", niches_dir: str = "",
    ) -> int:
        """Load available Blueprints from directories and niche conversion."""
        count = 0

        if blueprints_dir:
            bps = self._loader.load_directory(blueprints_dir, verify=False)
            for bp in bps:
                self._available_blueprints[bp.metadata.name] = bp
                count += 1

        if niches_dir:
            converter = NicheConverter()
            bps = converter.convert_directory(niches_dir)
            for bp in bps:
                self._available_blueprints[bp.metadata.name] = bp
                count += 1

        logger.info("OnboardingEngine: Loaded %d Blueprints", count)
        return count

    def list_available_blueprints(
        self, domain: str = "", tier: str = "",
    ) -> List[Dict[str, Any]]:
        """List available Blueprints with optional filtering."""
        results: List[Dict[str, Any]] = []
        for bp in self._available_blueprints.values():
            if domain and bp.metadata.domain != domain:
                continue
            if tier and bp.metadata.tier.value != tier:
                continue
            results.append({
                "name": bp.metadata.name,
                "domain": bp.metadata.domain,
                "subdomain": bp.metadata.subdomain,
                "description": bp.metadata.description,
                "tier": bp.metadata.tier.value,
                "scale": bp.metadata.scale,
                "entities": len(bp.db_schema.entities),
                "monitors": len(bp.monitor_hooks),
                "is_certified": bp.is_certified,
                "icon": bp.metadata.icon,
            })
        return results

    def list_domains(self) -> List[str]:
        """List all available Blueprint domains."""
        domains = set()
        for bp in self._available_blueprints.values():
            if bp.metadata.domain:
                domains.add(bp.metadata.domain)
        return sorted(domains)

    def select_blueprints(
        self, session: OnboardingSession, blueprint_names: List[str],
    ) -> bool:
        """Select Blueprints for the onboarding session."""
        for name in blueprint_names:
            if name not in self._available_blueprints:
                logger.warning("OnboardingEngine: Blueprint '%s' not found", name)
                return False

        selected_bps = [
            self._available_blueprints[n] for n in blueprint_names
        ]
        if len(selected_bps) > 1:
            from .validator import BlueprintValidatorV2
            validator = BlueprintValidatorV2()
            result = validator.validate_compatibility(selected_bps)
            if not result.is_valid:
                logger.warning(
                    "OnboardingEngine: Compatibility issues: %s", result.errors,
                )

        session.blueprint_names = blueprint_names
        self._complete_step(session, OnboardingStepType.SELECT_BLUEPRINT)
        self._update_monitor_step(session, selected_bps)
        return True

    # ── Step Navigation ────────────────────────────────────

    def advance_step(self, session: OnboardingSession) -> OnboardingSession:
        """Move to the next onboarding step."""
        if session.current_step < len(session.steps) - 1:
            session.current_step += 1
        return session

    def go_to_step(
        self, session: OnboardingSession, step_type: OnboardingStepType,
    ) -> Optional[OnboardingStep]:
        """Jump to a specific step type."""
        for i, step in enumerate(session.steps):
            if step.step_type == step_type:
                session.current_step = i
                return step
        return None

    def complete_current_step(
        self, session: OnboardingSession, config: Dict[str, Any],
    ) -> OnboardingSession:
        """Complete the current step with configuration data."""
        if session.current_step < len(session.steps):
            step = session.steps[session.current_step]
            step.config.update(config)
            step.completed = True
            if step.step_type == OnboardingStepType.IMPORT_DATA:
                session.import_data.update(config)
        return session

    # ── Completion ─────────────────────────────────────────

    def complete_onboarding(
        self, session: OnboardingSession,
    ) -> CompositionResult:
        """Complete the onboarding and compose the final Blueprint."""
        bps = [
            self._available_blueprints[name]
            for name in session.blueprint_names
            if name in self._available_blueprints
        ]

        if not bps:
            result = CompositionResult()
            result.warnings.append("No Blueprints selected")
            return result

        composed_result = self._composer.compose(bps)
        if composed_result.blueprint is not None:
            self._apply_user_config(composed_result.blueprint, session)
            for step in session.steps:
                if step.required:
                    step.completed = True
            session.completed_at = time.time()
            self._fire_hooks("onboarding_complete", composed_result.blueprint, session)

        return composed_result

    # ── Hooks ──────────────────────────────────────────────

    def register_hook(self, event: str, callback: Callable) -> None:
        """Register a callback for an onboarding event."""
        if event not in self._hooks:
            self._hooks[event] = []
        self._hooks[event].append(callback)

    def _fire_hooks(self, event: str, *args: Any) -> None:
        """Fire registered hooks for an event."""
        for callback in self._hooks.get(event, []):
            try:
                callback(*args)
            except Exception as e:
                logger.warning("OnboardingEngine: Hook error: %s", e)

    # ── Private Helpers ────────────────────────────────────

    def _complete_step(
        self, session: OnboardingSession, step_type: OnboardingStepType,
    ) -> None:
        """Mark a step as completed."""
        for step in session.steps:
            if step.step_type == step_type:
                step.completed = True

    def _update_monitor_step(
        self, session: OnboardingSession, selected_bps: List[CertifiedBlueprint],
    ) -> None:
        """Update the monitor configuration step with selected Blueprint monitors."""
        monitor_config: Dict[str, Any] = {}
        for bp in selected_bps:
            for hook in bp.monitor_hooks:
                monitor_config[hook.monitor_id] = {
                    "weight": hook.weight,
                    "interval_seconds": hook.interval_seconds,
                    "enabled": hook.enabled,
                    "notification_channel": hook.notification_channel,
                    "thresholds": hook.thresholds,
                }
        for step in session.steps:
            if step.step_type == OnboardingStepType.CONFIGURE_MONITORS:
                step.config["monitors"] = monitor_config

    def _apply_user_config(
        self, blueprint: CertifiedBlueprint, session: OnboardingSession,
    ) -> None:
        """Apply user configuration from onboarding steps to the Blueprint."""
        for step in session.steps:
            if step.step_type == OnboardingStepType.CONFIGURE_MONITORS:
                self._apply_monitor_config(blueprint, step.config)
            elif step.step_type == OnboardingStepType.CONFIGURE_NOTIFICATIONS:
                self._apply_notification_config(blueprint, step.config)
            elif step.step_type == OnboardingStepType.IMPORT_DATA:
                if session.import_data:
                    logger.info(
                        "OnboardingEngine: Import data with %d sources",
                        len(session.import_data),
                    )

    def _apply_monitor_config(
        self, blueprint: CertifiedBlueprint, config: Dict[str, Any],
    ) -> None:
        """Apply monitor threshold overrides."""
        monitors_config = config.get("monitors", {})
        for monitor_id, mc in monitors_config.items():
            found = False
            for hook in blueprint.monitor_hooks:
                if hook.monitor_id == monitor_id:
                    hook.thresholds = mc.get("thresholds", hook.thresholds)
                    hook.notification_channel = mc.get(
                        "notification_channel", hook.notification_channel,
                    )
                    hook.enabled = mc.get("enabled", hook.enabled)
                    found = True
                    break
            if not found:
                blueprint.add_monitor_hook(MonitorHook(
                    monitor_id=monitor_id,
                    weight=mc.get("weight", "lightweight"),
                    interval_seconds=mc.get("interval_seconds", 300),
                    thresholds=mc.get("thresholds", []),
                    notification_channel=mc.get("notification_channel", "log"),
                ))

    def _apply_notification_config(
        self, blueprint: CertifiedBlueprint, config: Dict[str, Any],
    ) -> None:
        """Apply notification channel overrides."""
        channels = config.get("channels", {})
        if channels:
            for hook in blueprint.monitor_hooks:
                override = channels.get(hook.monitor_id)
                if override:
                    hook.notification_channel = override
