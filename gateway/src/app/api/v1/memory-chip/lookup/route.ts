// ─── POST /api/v1/memory-chip/lookup ────────────────────────────────────
// Lookup a semantic mapping by text. Validates tenant access to memory chip.

import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { searchOntologyBase } from '@/lib/memory-chip';

interface LookupRequestBody {
  text: string;
  tenant_id?: string;
}

export async function POST(request: NextRequest) {
  try {
    const body: LookupRequestBody = await request.json();

    // Validate required fields
    if (!body.text || typeof body.text !== 'string' || body.text.trim().length === 0) {
      return NextResponse.json(
        { success: false, error: 'Missing required field: text (non-empty string)' },
        { status: 400 },
      );
    }

    const tenantId = body.tenant_id || '__anonymous__';
    const searchText = body.text.trim().toLowerCase();

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
            error: 'Subscription is not active. Memory chip access requires an active subscription.',
            tenant_id: tenantId,
          },
          { status: 403 },
        );
      }
    }

    // Try to find an existing approved mapping in the database
    const existingMapping = await db.memoryMapping.findFirst({
      where: {
        tenantId,
        approved: true,
        OR: [
          { origin: { equals: searchText, mode: 'insensitive' } },
          { destination: { equals: searchText, mode: 'insensitive' } },
        ],
      },
      orderBy: { confidence: 'desc' },
    });

    if (existingMapping) {
      const mapping = {
        mapping_id: existingMapping.mappingId,
        origin: existingMapping.origin,
        relation: existingMapping.relation,
        destination: existingMapping.destination,
        mechanism: existingMapping.mechanism as 'schema_drift' | 'intent_routing' | 'policy_refinement' | 'ontology_base',
        confidence: existingMapping.confidence,
        tenant_id: existingMapping.tenantId,
        created_at: existingMapping.createdAt.getTime(),
        approved: existingMapping.approved,
        merkle_hash: existingMapping.merkleHash,
      };

      return NextResponse.json({
        success: true,
        data: {
          cache_hit: true,
          mapping,
          origin: searchText,
          destination: existingMapping.destination,
        },
      });
    }

    // No mapping found in DB — search the ontology base
    const ontologyResults = searchOntologyBase(searchText);

    if (ontologyResults.length > 0) {
      const bestMatch = ontologyResults[0];
      const mapping = {
        mapping_id: `ontology_${bestMatch.term}`,
        origin: bestMatch.term,
        relation: 'maps_to',
        destination: bestMatch.mapped_to,
        mechanism: 'ontology_base' as const,
        confidence: bestMatch.confidence,
        tenant_id: tenantId,
        created_at: Date.now(),
        approved: false,
        merkle_hash: null,
      };

      return NextResponse.json({
        success: true,
        data: {
          cache_hit: false,
          mapping,
          origin: searchText,
          destination: bestMatch.mapped_to,
        },
      });
    }

    // No mapping found anywhere
    return NextResponse.json({
      success: true,
      data: {
        cache_hit: false,
        mapping: null,
        origin: searchText,
        destination: '',
      },
    });
  } catch (error) {
    console.error('[memory-chip/lookup] Error:', error);
    return NextResponse.json(
      { success: false, error: 'Internal server error' },
      { status: 500 },
    );
  }
}
