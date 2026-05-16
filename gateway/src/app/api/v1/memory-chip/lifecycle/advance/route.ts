// ─── POST /api/v1/memory-chip/lifecycle/advance ────────────────────────
// Advance a lifecycle episode to the next phase.

import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { isValidLifecyclePhase, getNextPhases, type LifecyclePhase } from '@/lib/memory-chip';

interface AdvanceEpisodeRequestBody {
  episode_id: string;
  phase: string;
}

export async function POST(request: NextRequest) {
  try {
    const body: AdvanceEpisodeRequestBody = await request.json();

    // Validate required fields
    if (!body.episode_id || typeof body.episode_id !== 'string' || body.episode_id.trim().length === 0) {
      return NextResponse.json(
        { success: false, error: 'Missing required field: episode_id (non-empty string)' },
        { status: 400 },
      );
    }
    if (!body.phase || typeof body.phase !== 'string' || body.phase.trim().length === 0) {
      return NextResponse.json(
        { success: false, error: 'Missing required field: phase (non-empty string)' },
        { status: 400 },
      );
    }

    // Validate phase value
    if (!isValidLifecyclePhase(body.phase)) {
      return NextResponse.json(
        {
          success: false,
          error: `Invalid phase: "${body.phase}". Valid phases: observe, hypothesize, validate, approve, deploy, retire`,
        },
        { status: 400 },
      );
    }

    const targetPhase = body.phase as LifecyclePhase;

    // Find the episode
    const episode = await db.memoryLifecycleEpisode.findUnique({
      where: { episodeId: body.episode_id.trim() },
    });

    if (!episode) {
      return NextResponse.json(
        { success: false, error: `Episode not found: ${body.episode_id}` },
        { status: 404 },
      );
    }

    if (episode.status !== 'active') {
      return NextResponse.json(
        {
          success: false,
          error: `Episode is not active (current status: ${episode.status}). Only active episodes can be advanced.`,
          episode_id: body.episode_id,
        },
        { status: 400 },
      );
    }

    // Validate phase transition
    const currentPhase = episode.currentPhase as LifecyclePhase;
    const validNextPhases = getNextPhases(currentPhase);

    if (!validNextPhases.includes(targetPhase)) {
      return NextResponse.json(
        {
          success: false,
          error: `Invalid phase transition: "${currentPhase}" → "${targetPhase}". Valid next phases from "${currentPhase}": [${validNextPhases.join(', ')}]`,
          episode_id: body.episode_id,
          current_phase: currentPhase,
          requested_phase: targetPhase,
        },
        { status: 400 },
      );
    }

    // Update phase history
    const phaseHistory = JSON.parse(episode.phaseHistory || '[]');
    phaseHistory.push({ phase: targetPhase, timestamp: new Date().toISOString() });

    // Determine if episode is now completed (retire phase)
    const newStatus = targetPhase === 'retire' ? 'completed' : 'active';
    const completedAt = targetPhase === 'retire' ? new Date() : null;

    // If advancing to 'approve' phase, check if the mapping needs approval
    if (targetPhase === 'approve') {
      const mapping = await db.memoryMapping.findUnique({
        where: { mappingId: episode.mappingId },
      });

      if (mapping && !mapping.approved) {
        // Episode cannot advance past 'approve' without HITL approval
        // We allow the transition to 'approve' but note it in metadata
        const metadata = JSON.parse(episode.metadata || '{}');
        metadata.awaiting_approval = true;
        await db.memoryLifecycleEpisode.update({
          where: { episodeId: body.episode_id.trim() },
          data: {
            currentPhase: targetPhase,
            phaseHistory: JSON.stringify(phaseHistory),
            metadata: JSON.stringify(metadata),
            updatedAt: new Date(),
          },
        });

        return NextResponse.json({
          success: true,
          data: {
            episode_id: body.episode_id,
            previous_phase: currentPhase,
            current_phase: targetPhase,
            status: 'active',
            awaiting_approval: true,
            message: 'Episode advanced to "approve" phase. Mapping requires HITL approval before advancing further.',
          },
        });
      }
    }

    // Update the episode
    await db.memoryLifecycleEpisode.update({
      where: { episodeId: body.episode_id.trim() },
      data: {
        currentPhase: targetPhase,
        phaseHistory: JSON.stringify(phaseHistory),
        status: newStatus,
        completedAt,
        updatedAt: new Date(),
      },
    });

    // If deploying, update the mapping confidence
    if (targetPhase === 'deploy') {
      await db.memoryMapping.update({
        where: { mappingId: episode.mappingId },
        data: {
          confidence: 0.9, // Deployed mappings get high confidence
          updatedAt: new Date(),
        },
      });
    }

    return NextResponse.json({
      success: true,
      data: {
        episode_id: body.episode_id,
        previous_phase: currentPhase,
        current_phase: targetPhase,
        status: newStatus,
        phase_history: phaseHistory,
      },
    });
  } catch (error) {
    console.error('[memory-chip/lifecycle/advance] Error:', error);
    return NextResponse.json(
      { success: false, error: 'Internal server error' },
      { status: 500 },
    );
  }
}
