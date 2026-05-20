// ─── POST /api/v1/memory-chip/lifecycle/start ──────────────────────────
// Start a new learning lifecycle episode.

import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';
import {
  isValidMechanism,
  type MechanismType,
  getSubscriptionFeatures,
  type SubscriptionTier,
} from '@/lib/memory-chip';

interface StartEpisodeRequestBody {
  origin: string;
  relation: string;
  destination: string;
  mechanism: string;
  tenant_id?: string;
}

export async function POST(request: NextRequest) {
  try {
    const body: StartEpisodeRequestBody = await request.json();

    // Validate required fields
    if (!body.origin || typeof body.origin !== 'string' || body.origin.trim().length === 0) {
      return NextResponse.json(
        { success: false, error: 'Missing required field: origin (non-empty string)' },
        { status: 400 },
      );
    }
    if (!body.relation || typeof body.relation !== 'string' || body.relation.trim().length === 0) {
      return NextResponse.json(
        { success: false, error: 'Missing required field: relation (non-empty string)' },
        { status: 400 },
      );
    }
    if (!body.destination || typeof body.destination !== 'string' || body.destination.trim().length === 0) {
      return NextResponse.json(
        { success: false, error: 'Missing required field: destination (non-empty string)' },
        { status: 400 },
      );
    }
    if (!body.mechanism || typeof body.mechanism !== 'string') {
      return NextResponse.json(
        { success: false, error: 'Missing required field: mechanism' },
        { status: 400 },
      );
    }

    if (!isValidMechanism(body.mechanism)) {
      return NextResponse.json(
        {
          success: false,
          error: `Invalid mechanism: "${body.mechanism}". Must be one of: schema_drift, intent_routing, policy_refinement, ontology_base`,
        },
        { status: 400 },
      );
    }

    const tenantId = body.tenant_id || '__anonymous__';
    const mechanism = body.mechanism as MechanismType;

    // Check tenant subscription for lifecycle access
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
            error: 'Subscription is not active. Cannot start lifecycle episodes.',
            tenant_id: tenantId,
          },
          { status: 403 },
        );
      }

      // Check mechanism access
      const tierMapping: Record<string, SubscriptionTier> = {
        starter: 'starter',
        business: 'business',
        enterprise: 'enterprise',
        on_premise_enterprise: 'on_premise',
        trial: 'starter',
      };
      const mappedTier = tierMapping[subscription.tier] || 'starter';
      const features = getSubscriptionFeatures(mappedTier);

      if (!features.mechanisms_allowed.includes(mechanism)) {
        return NextResponse.json(
          {
            success: false,
            error: `Mechanism "${mechanism}" is not available for tier "${subscription.tier}". Allowed: ${features.mechanisms_allowed.join(', ')}`,
            tenant_id: tenantId,
          },
          { status: 403 },
        );
      }
    }

    // First, create the mapping (unapproved) for this episode
    const mappingId = `map_${Date.now()}_${Math.random().toString(36).substring(2, 10)}`;

    const mapping = await db.memoryMapping.create({
      data: {
        mappingId,
        origin: body.origin.trim(),
        relation: body.relation.trim(),
        destination: body.destination.trim(),
        mechanism,
        confidence: 0.0,
        tenantId,
        approved: false,
        metadata: JSON.stringify({ source: 'lifecycle_episode' }),
      },
    });

    // Create the lifecycle episode starting at 'observe' phase
    const episodeId = `ep_${Date.now()}_${Math.random().toString(36).substring(2, 10)}`;
    const now = new Date();

    const episode = await db.memoryLifecycleEpisode.create({
      data: {
        episodeId,
        mappingId: mapping.mappingId,
        currentPhase: 'observe',
        phaseHistory: JSON.stringify([{ phase: 'observe', timestamp: now.toISOString() }]),
        status: 'active',
        tenantId,
        metadata: JSON.stringify({
          mechanism,
          origin: body.origin.trim(),
          destination: body.destination.trim(),
        }),
      },
    });

    return NextResponse.json(
      {
        success: true,
        data: {
          episode_id: episode.episodeId,
          mapping: {
            mapping_id: mapping.mappingId,
            origin: mapping.origin,
            relation: mapping.relation,
            destination: mapping.destination,
            mechanism: mapping.mechanism as MechanismType,
            confidence: mapping.confidence,
            tenant_id: mapping.tenantId,
            created_at: mapping.createdAt.getTime(),
            approved: mapping.approved,
            merkle_hash: mapping.merkleHash,
          },
          current_phase: episode.currentPhase,
          created_at: episode.createdAt.getTime(),
          updated_at: episode.updatedAt.getTime(),
        },
      },
      { status: 201 },
    );
  } catch (error) {
    console.error('[memory-chip/lifecycle/start] Error:', error);
    return NextResponse.json(
      { success: false, error: 'Internal server error' },
      { status: 500 },
    );
  }
}
