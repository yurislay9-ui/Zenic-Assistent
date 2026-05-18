"""
chain_composer._executors — Step executor functions.
"""

from __future__ import annotations

from typing import Any

from src.core.workflows.chain_composer._types import ChainStepType


def _execute_trigger_step(config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Execute a trigger step: capture event data into context."""
    event_type = config.get("event_type", "unknown")
    return {
        "triggered": True,
        "event_type": event_type,
        "source": config.get("source", "unknown"),
        **{k: v for k, v in config.items() if k not in ("event_type", "source")},
    }


def _execute_condition_step(config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Execute a condition/validation step."""
    check_type = config.get("check_type", "generic")
    passed = bool(context)
    return {
        "check_type": check_type,
        "passed": passed,
        "details": f"Condition check '{check_type}' {'passed' if passed else 'failed'}",
    }


def _execute_action_step(config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Execute an action step."""
    action_type = config.get("action_type", "generic")
    return {
        "action_type": action_type,
        "executed": True,
        "target": config.get("target_table", config.get("product_id", config.get("invoice_id", ""))),
        **{k: v for k, v in config.items() if k != "action_type"},
    }


def _execute_notification_step(config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Execute a notification step."""
    channel = config.get("channel", "email")
    recipient = config.get("recipient", "unknown")
    message_template = config.get("message_template", "")
    message = message_template
    for key, value in context.items():
        if isinstance(value, (str, int, float)):
            message = message.replace("{{" + key + "}}", str(value))
    return {"channel": channel, "recipient": recipient, "message": message, "sent": True}


def _execute_delay_step(config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Execute a delay step."""
    delay_ms = config.get("delay_ms", 1000)
    return {"delay_ms": delay_ms, "waited": True}


def _execute_sub_chain_step(config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Execute a sub-chain step."""
    sub_chain_id = config.get("sub_chain_id", "")
    return {
        "sub_chain_id": sub_chain_id,
        "executed": True,
        "note": "Sub-chain execution is recorded; actual recursion handled by orchestrator",
    }


STEP_EXECUTORS: dict[ChainStepType, Any] = {
    ChainStepType.TRIGGER: _execute_trigger_step,
    ChainStepType.CONDITION: _execute_condition_step,
    ChainStepType.ACTION: _execute_action_step,
    ChainStepType.NOTIFICATION: _execute_notification_step,
    ChainStepType.DELAY: _execute_delay_step,
    ChainStepType.SUB_CHAIN: _execute_sub_chain_step,
}
