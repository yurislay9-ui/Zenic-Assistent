/**
 * POST /api/v1/memory-chip/mappings
 *
 * Insert a new semantic mapping into the Memory Chip.
 * Validates subscription tier before allowing insertion.
 */

import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';

// Subscription tier limits
const TIER_LIMITS: Record<string, { mechanisms: string[]; maxMappings: number }> = {
  starter: { mechanisms: ['schema_drift'], maxMappings: 10 },
  business: { mechanisms: ['schema_drift', 'intent_routing'], maxMappings: 50 },
  enterprise: {
    mechanisms: ['schema_drift', 'intent_routing', 'policy_refinement'],
    maxMappings: -1,
  },
  on_premise: {
    mechanisms: ['schema_drift', 'intent_routing', 'policy_refinement', 'ontology_base'],
    maxMappings: -1,
  },
};

const VALID_MECHANISMS = ['schema_drift', 'intent_routing', 'policy_refinement', 'ontology_base'];
const VALID_RELATIONS = ['synonym_of', 'maps_to', 'equivalent_to', 'triggers', 'refines', 'overrides'];

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const {
      origin,
      relation,
      destination,
      mechanism,
      tenant_id = '__anonymous__',
      tier = 'enterprise',
    } = body;

    // ── Validate required fields ──
    if (!origin || typeof origin !== 'string' || origin.trim().length === 0) {
      return NextResponse.json(
        { success: false, error: 'origin is required and must be a non-empty string' },
        { status: 400 },
      );
    }
    if (!relation || typeof relation !== 'string' || !VALID_RELATIONS.includes(relation)) {
      return NextResponse.json(
        { success: false, error: `relation must be one of: ${VALID_RELATIONS.join(', ')}` },
        { status: 400 },
      );
    }
    if (!destination || typeof destination !== 'string' || destination.trim().length === 0) {
      return NextResponse.json(
        { success: false, error: 'destination is required and must be a non-empty string' },
        { status: 400 },
      );
    }
    if (!mechanism || !VALID_MECHANISMS.includes(mechanism)) {
      return NextResponse.json(
        { success: false, error: `mechanism must be one of: ${VALID_MECHANISMS.join(', ')}` },
        { status: 400 },
      );
    }

    // ── Check subscription tier ──
    const tierConfig = TIER_LIMITS[tier] || TIER_LIMITS.enterprise;
    if (!tierConfig.mechanisms.includes(mechanism)) {
      return NextResponse.json(
        {
          success: false,
          error: `Mechanism '${mechanism}' not available for tier '${tier}'. Available: ${tierConfig.mechanisms.join(', ')}`,
        },
        { status: 403 },
      );
    }

    // ── Check mapping quota ──
    if (tierConfig.maxMappings > 0) {
      const currentCount = await db.memoryMapping.count({
        where: { tenant_id },
      });
      if (currentCount >= tierConfig.maxMappings) {
        return NextResponse.json(
          {
            success: false,
            error: `Mapping quota exceeded for tier '${tier}'. Maximum: ${tierConfig.maxMappings}, Current: ${currentCount}`,
          },
          { status: 403 },
        );
      }
    }

    // ── Generate mapping ID ──
    const mappingId = `map-${Date.now()}-${Math.random().toString(36).substring(2, 10)}`;

    // ── Insert mapping ──
    const mapping = await db.memoryMapping.create({
      data: {
        mapping_id: mappingId,
        origin: origin.trim(),
        relation,
        destination: destination.trim(),
        mechanism,
        tenant_id,
        approved: false,
      },
    });

    return NextResponse.json({
      success: true,
      data: {
        mapping_id: mapping.mapping_id,
        origin: mapping.origin,
        relation: mapping.relation,
        destination: mapping.destination,
        mechanism: mapping.mechanism,
        tenant_id: mapping.tenant_id,
        approved: mapping.approved,
      },
    });
  } catch (error) {
    console.error('[memory-chip/mappings] Error:', error);
    return NextResponse.json(
      { success: false, error: 'Internal server error' },
      { status: 500 },
    );
  }
}

/**
 * GET /api/v1/memory-chip/mappings
 *
 * List all mappings for a tenant, with optional filtering.
 */
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const tenantId = searchParams.get('tenant_id') || '__anonymous__';
    const mechanism = searchParams.get('mechanism');
    const approved = searchParams.get('approved');

    const where: Record<string, unknown> = { tenant_id: tenantId };
    if (mechanism) where.mechanism = mechanism;
    if (approved !== null) where.approved = approved === 'true';

    const mappings = await db.memoryMapping.findMany({
      where,
      orderBy: { created_at: 'desc' },
      take: 100,
    });

    return NextResponse.json({
      success: true,
      data: mappings,
      count: mappings.length,
    });
  } catch (error) {
    console.error('[memory-chip/mappings-list] Error:', error);
    return NextResponse.json(
      { success: false, error: 'Internal server error' },
      { status: 500 },
    );
  }
}
