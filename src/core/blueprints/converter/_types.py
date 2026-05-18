"""Types and constants for converter."""

from __future__ import annotations
import logging
from typing import Dict

from ..types import BlueprintTier, BlueprintMetadataV2, DBSchema, DBEntitySchema, DBFieldSchema, BusinessRuleDef, ActionTemplateDef, MonitorHook
from ..convert_parts import BLOCK_EXECUTOR_MAP, parse_entity_fields, map_trigger_to_monitor, determine_monitor_weight, determine_notification_channel
from ..schema import CertifiedBlueprint

logger = logging.getLogger(__name__)

_SENSITIVITY_TIER_MAP: Dict[str, BlueprintTier] = {
    "low": BlueprintTier.FREE,
    "medium": BlueprintTier.FREE,
    "high": BlueprintTier.PRO,
    "critical": BlueprintTier.ENTERPRISE,
}
