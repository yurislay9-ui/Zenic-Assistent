// ─── Zenic-Agents v3 — Subscription API: Create Payment ──────────────
// POST /api/v1/subscription/payment — Create a USDT TRC20 payment

import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';
import {
  TIER_PRICES,
  ADD_ONS,
  SubscriptionTierName,
} from '@/lib/subscription/types';

const COMPANY_WALLET = process.env.USDT_TRC20_COMPANY_WALLET || 'TN7gR3kfdEkdk5dKz9PfeXf3qGxBfKs2Qy';

export async function POST(req: NextRequest) {
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

    const validTiers: SubscriptionTierName[] = ['starter', 'business', 'enterprise', 'on_premise_enterprise'];
    if (!validTiers.includes(body.tier as SubscriptionTierName)) {
      return NextResponse.json(
        { error: `Invalid tier. Must be one of: ${validTiers.join(', ')}` },
        { status: 400 },
      );
    }

    const tier = body.tier as SubscriptionTierName;
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

    // Calculate amount
    const tierPrice = TIER_PRICES[tier];
    const baseAmount = billingCycle === 'annual' ? tierPrice.annual : tierPrice.monthly;
    const addOnCost = ADD_ONS
      .filter(a => addOnIds.includes(a.id))
      .reduce((sum, a) => sum + a.monthlyPriceUsdt, 0);

    const includesSetupFee = body.includesSetupFee ?? false;
    const setupFeeAmount = includesSetupFee ? tierPrice.setup : 0;

    const totalAmount = baseAmount + addOnCost + setupFeeAmount;

    // Payment expires in 24 hours
    const expiresAt = new Date(Date.now() + 24 * 60 * 60 * 1000);

    const payment = await db.usdtPaymentRecord.create({
      data: {
        subscriptionId: subscription.id,
        tenantId: body.tenantId,
        amountUsdt: totalAmount,
        method: 'manual',
        companyWallet: COMPANY_WALLET,
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
            walletAddress: COMPANY_WALLET,
            amount: totalAmount,
            expiresAt,
          },
        },
      },
      { status: 201 },
    );
  } catch (error) {
    console.error('[Subscription Payment POST]', error);
    return NextResponse.json(
      { error: 'Internal server error', details: String(error) },
      { status: 500 },
    );
  }
}
