// ─── Zenic-Agents v3 — Subscription API: Get Tiers ───────────────────
// GET /api/v1/subscription/tiers — Get all available tiers with features and pricing

import { NextResponse } from 'next/server';
import {
  TIER_PRICES,
  TIER_DISPLAY_NAMES,
  TIER_RANK,
  TIER_LIMITS,
  MEMORY_TIER_CONFIG,
  FEATURE_GATES,
  ADD_ONS,
  SubscriptionTierName,
} from '@/lib/subscription/types';

const TIER_NAMES: SubscriptionTierName[] = ['starter', 'business', 'enterprise', 'on_premise_enterprise'];

export async function GET() {
  try {
    const tiers = TIER_NAMES.map(tier => {
      const limits = TIER_LIMITS[tier];
      const memoryConfig = MEMORY_TIER_CONFIG[tier];
      const features = FEATURE_GATES.filter(
        g => TIER_RANK[tier] >= TIER_RANK[g.minimumTier],
      );
      const unavailableFeatures = FEATURE_GATES.filter(
        g => TIER_RANK[tier] < TIER_RANK[g.minimumTier],
      );

      // Convert Infinity values to null for JSON serialization
      const serializedLimits: Record<string, number | null> = {};
      for (const [key, value] of Object.entries(limits)) {
        if (typeof value === 'boolean') {
          serializedLimits[key] = value ? 1 : 0;
        } else if (value === Infinity) {
          serializedLimits[key] = null;
        } else {
          serializedLimits[key] = value;
        }
      }

      const serializedMemoryConfig: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(memoryConfig)) {
        if (value === Infinity) {
          serializedMemoryConfig[key] = null;
        } else {
          serializedMemoryConfig[key] = value;
        }
      }

      return {
        name: tier,
        displayName: TIER_DISPLAY_NAMES[tier],
        rank: TIER_RANK[tier],
        pricing: TIER_PRICES[tier],
        limits: serializedLimits,
        memoryConfig: serializedMemoryConfig,
        features: features.map(f => ({
          feature: f.feature,
          description: f.description,
          availableAsAddon: f.availableAsAddon,
        })),
        unavailableFeatures: unavailableFeatures.map(f => ({
          feature: f.feature,
          description: f.description,
          minimumTier: f.minimumTier,
          availableAsAddon: f.availableAsAddon,
          addonId: f.addonId,
        })),
        compatibleAddOns: ADD_ONS.filter(a => a.compatibleTiers.includes(tier)),
      };
    });

    return NextResponse.json({
      data: {
        tiers,
        addOns: ADD_ONS,
      },
    });
  } catch (error) {
    console.error('[Subscription Tiers GET]', error);
    return NextResponse.json(
      { error: 'Internal server error', details: String(error) },
      { status: 500 },
    );
  }
}
