// ─── POST /api/v1/memory-chip/adapt ─────────────────────────────────────
// Try to adapt a failed field using learned mappings.

import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';

interface AdaptRequestBody {
  failed_field: string;
  tenant_id?: string;
}

export async function POST(request: NextRequest) {
  try {
    const body: AdaptRequestBody = await request.json();

    // Validate required fields
    if (!body.failed_field || typeof body.failed_field !== 'string' || body.failed_field.trim().length === 0) {
      return NextResponse.json(
        { success: false, error: 'Missing required field: failed_field (non-empty string)' },
        { status: 400 },
      );
    }

    const tenantId = body.tenant_id || '__anonymous__';
    const failedField = body.failed_field.trim().toLowerCase();

    // Check tenant subscription for memory chip access
    if (tenantId !== '__anonymous__') {
      const subscription = await db.subscription.findUnique({
        where: { tenantId },
        select: { tier: true, status: true },
      });

      if (!subscription) {
        return NextResponse.json(
          { success: false, error: 'No subscription found for this tenant', tenant_id: tenantId },
          { status: 403 },
        );
      }

      const activeStatuses = ['trial', 'active'];
      if (!activeStatuses.includes(subscription.status)) {
        return NextResponse.json(
          {
            success: false,
            error: 'Subscription is not active. Memory chip adapt requires an active subscription.',
            tenant_id: tenantId,
          },
          { status: 403 },
        );
      }
    }

    // Try to find an approved mapping where the origin matches the failed field
    // This implements GRIETA 1: dag_adapter try_adapt() — cache lookup → SQLite lookup → inject corrected parameter
    const mapping = await db.memoryMapping.findFirst({
      where: {
        tenantId,
        approved: true,
        origin: { equals: failedField, mode: 'insensitive' },
      },
      orderBy: { confidence: 'desc' },
    });

    if (mapping) {
      return NextResponse.json({
        success: true,
        data: {
          adapted: true,
          corrected_field: mapping.destination,
          mapping_id: mapping.mappingId,
        },
      });
    }

    // No adaptation found — the failed field cannot be corrected
    return NextResponse.json({
      success: true,
      data: {
        adapted: false,
        corrected_field: null,
        mapping_id: null,
      },
    });
  } catch (error) {
    console.error('[memory-chip/adapt] Error:', error);
    return NextResponse.json(
      { success: false, error: 'Internal server error' },
      { status: 500 },
    );
  }
}
