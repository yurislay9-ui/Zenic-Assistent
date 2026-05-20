// ─── Zenic-Agents v3 — Subscription API: Create Payment ──────────────
// POST /api/v1/subscription/payment — Create a USDT TRC20 payment
// INVARIANT 4: Platform wallet must be configured — fail-closed if missing.

import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { calculatePricing, PAID_TIER_NAMES, SubscriptionTierName as PricingTierName } from '@/lib/pricing-engine';
import { requireTenantAuth, verifyTenantOwnership } from '@/lib/subscription/auth-helpers';

/**
 * Get the company wallet from environment variable.
 * INVARIANT 4: Fail-closed — never use a hardcoded fallback wallet.
 */
function getCompanyWallet(): string {
  const wallet = process.env.USDT_TRC20_COMPANY_WALLET;
  if (!wallet) {
    throw new Error('USDT_TRC20_COMPANY_WALLET env var is required. Payment creation denied.');
  }
  if (!wallet.startsWith('T') || wallet.length !== 34) {
    throw new Error('USDT_TRC20_COMPANY_WALLET is not a valid TRC20 address.');
  }
  return wallet;
}

const VALID_TIERS = ['starter', 'business', 'enterprise', 'on_premise_enterprise'] as const;

export async function POST(req: NextRequest) {
  // Verify tenant identity
  const auth = requireTenantAuth(req);
  if (auth instanceof Response) return auth;

  try {
    const body = await req.json() as {
      tenantId?: string;
      tier?: string;
      addOnIds?: string[];
      includesSetupFee?: boolean;
      billingCycle?: 'monthly' | 'annual';
    };

    if (!body.tenantId || !body.tier) {
      return NextResponse.json(
        { error: 'tenantId and tier are required' },
        { status: 400 },
      );
    }

    // Verify tenant ownership: caller can only create payments for their own tenant
    if (!verifyTenantOwnership(auth, body.tenantId)) {
      return NextResponse.json(
        { error: 'Access denied' },
        { status: 403 },
      );
    }

    if (!VALID_TIERS.includes(body.tier as typeof VALID_TIERS[number])) {
      return NextResponse.json(
        { error: `Invalid tier. Must be one of: ${VALID_TIERS.join(', ')}` },
        { status: 400 },
      );
    }

    const tier = body.tier as typeof VALID_TIERS[number];
    const addOnIds = body.addOnIds ?? [];
    const billingCycle = body.billingCycle ?? 'monthly';

    // Verify subscription exists
    const subscription = await db.tenantSubscription.findUnique({
      where: { tenantId: body.tenantId },
    });

    if (!subscription) {
      return NextResponse.json(
        { error: 'Subscription not found. Sign up first.' },
        { status: 404 },
      );
    }

    // Calculate amount using the canonical pricing engine (WASM-first, TS fallback)
    const pricing = calculatePricing(tier, addOnIds);
    const baseAmount = billingCycle === 'annual' ? pricing.annual_price_usdt : pricing.monthly_price_usdt;
    const addOnCost = pricing.add_ons_monthly_usdt;

    const includesSetupFee = body.includesSetupFee ?? false;
    const setupFeeAmount = includesSetupFee ? pricing.setup_fee_usdt : 0;

    const totalAmount = baseAmount + addOnCost + setupFeeAmount;

    // Get company wallet — fail-closed if not configured (BUG #2 FIX)
    let companyWallet: string;
    try {
      companyWallet = getCompanyWallet();
    } catch {
      return NextResponse.json(
        { error: 'Payment processing unavailable', message: 'Platform wallet not configured' },
        { status: 503 },
      );
    }

    // Payment expires in 24 hours
    const expiresAt = new Date(Date.now() + 24 * 60 * 60 * 1000);

    const payment = await db.usdtPaymentRecord.create({
      data: {
        subscriptionId: subscription.id,
        tenantId: body.tenantId,
        amountUsdt: totalAmount,
        method: 'manual',
        companyWallet,
        status: 'pending',
        includesSetupFee,
        setupFeeAmountUsdt: setupFeeAmount,
        verificationAttempts: 0,
        maxVerificationAttempts: 5,
        expiresAt,
      },
    });

    return NextResponse.json(
      {
        data: {
          payment,
          paymentInfo: {
            network: 'TRC20',
            token: 'USDT',
            walletAddress: companyWallet,
            amount: totalAmount,
            expiresAt,
          },
        },
      },
      { status: 201 },
    );
  } catch (error) {
    console.error('[Subscription Payment POST]', error);
    // BUG #9 FIX: Never expose String(error) to client
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 },
    );
  }
}
