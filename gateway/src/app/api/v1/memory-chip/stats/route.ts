// ─── GET /api/v1/memory-chip/stats ─────────────────────────────────────
// Get memory chip statistics.

import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const tenantId = searchParams.get('tenant_id') || '__anonymous__';

    // Build the where clause based on tenant
    const whereClause = tenantId === '__anonymous__'
      ? {}
      : { tenantId };

    // Get total counts
    const totalMappings = await db.memoryMapping.count({ where: whereClause });
    const approvedMappings = await db.memoryMapping.count({
      where: { ...whereClause, approved: true },
    });
    const pendingMappings = await db.memoryMapping.count({
      where: { ...whereClause, approved: false },
    });

    // Get mechanism breakdown
    const allMappings = await db.memoryMapping.findMany({
      where: whereClause,
      select: { mechanism: true },
    });

    const mechanisms: Record<string, number> = {};
    for (const mapping of allMappings) {
      mechanisms[mapping.mechanism] = (mechanisms[mapping.mechanism] || 0) + 1;
    }

    // Get lifecycle episode count for LRU size approximation
    const activeEpisodes = await db.memoryLifecycleEpisode.count({
      where: {
        ...(tenantId === '__anonymous__' ? {} : { tenantId }),
        status: 'active',
      },
    });

    // Calculate approximate cache hit rate based on approved vs total ratio
    const cacheHitRate = totalMappings > 0 ? approvedMappings / totalMappings : 0;

    return NextResponse.json({
      success: true,
      data: {
        total_mappings: totalMappings,
        approved_mappings: approvedMappings,
        pending_mappings: pendingMappings,
        cache_hit_rate: Math.round(cacheHitRate * 1000) / 1000, // 3 decimal places
        mechanisms,
        lru_size: activeEpisodes,
        lru_capacity: 1000, // Default capacity
      },
    });
  } catch (error) {
    console.error('[memory-chip/stats] Error:', error);
    return NextResponse.json(
      { success: false, error: 'Internal server error' },
      { status: 500 },
    );
  }
}
