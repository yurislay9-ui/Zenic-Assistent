// ─── GET /api/v1/memory-chip/subscription/features ─────────────────────
// Get subscription tier features for the memory chip.

import { NextRequest, NextResponse } from 'next/server';
import {
  isValidTier,
  getSubscriptionFeatures,
  SUBSCRIPTION_TIERS,
  type SubscriptionTier,
  type SubscriptionFeatures,
} from '@/lib/memory-chip';

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const tierParam = searchParams.get('tier');

    if (!tierParam) {
      // Return all tier features if no specific tier requested
      const allFeatures: Record<string, SubscriptionFeatures> = {};
      for (const [key, _config] of Object.entries(SUBSCRIPTION_TIERS)) {
        allFeatures[key] = getSubscriptionFeatures(key as SubscriptionTier);
      }

      return NextResponse.json({
        success: true,
        data: allFeatures,
        meta: {
          tiers_available: Object.keys(SUBSCRIPTION_TIERS),
        },
      });
    }

    // Validate the tier parameter
    if (!isValidTier(tierParam)) {
      return NextResponse.json(
        {
          success: false,
          error: `Invalid tier: "${tierParam}". Valid tiers: ${Object.keys(SUBSCRIPTION_TIERS).join(', ')}`,
        },
        { status: 400 },
      );
    }

    const features = getSubscriptionFeatures(tierParam as SubscriptionTier);

    return NextResponse.json({
      success: true,
      data: features,
      meta: {
        tier: tierParam,
        display_name: SUBSCRIPTION_TIERS[tierParam as SubscriptionTier].name,
      },
    });
  } catch (error) {
    console.error('[memory-chip/subscription/features] Error:', error);
    return NextResponse.json(
      { success: false, error: 'Internal server error' },
      { status: 500 },
    );
  }
}
