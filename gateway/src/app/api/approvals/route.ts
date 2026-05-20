import { NextRequest, NextResponse } from 'next/server';
import { getAuthUser } from '@/lib/auth';
import { checkFeatureGate } from '@/lib/feature-gates';
import {
  createApprovalRequest,
  reviewApprovalRequest,
  getPendingApprovals,
  getApprovalHistory,
  requiresApproval,
  determineRiskLevel,
} from '@/lib/hitl';
import { governor } from '@/lib/resource-governor';

/**
 * GET /api/approvals
 * List pending approval requests or approval history.
 * 
 * #41 Fix: Requires authentication.
 * #42 Fix: Feature gate "approval:list" is checked server-side.
 * #58 Fix: ResourceGovernor — rate limited + concurrency.
 */
export async function GET(req: NextRequest) {
  const user = await getAuthUser(req);
  if (!user) {
    return NextResponse.json({ error: 'Authentication required' }, { status: 401 });
  }

  // #58: Governor check
  const clientIp = req.headers.get('x-client-ip') || req.headers.get('x-forwarded-for') || 'unknown';
  const verdict = governor.check(clientIp, user.id, 'approval:read');
  if (!verdict.allowed) {
    return NextResponse.json(
      { error: verdict.reason, code: verdict.code, retryAfterMs: verdict.retryAfterMs },
      { status: 429 }
    );
  }

  try {
    // Check feature gate
    const gate = await checkFeatureGate('approval:list', user.role);
    if (!gate.allowed) {
      return NextResponse.json({ error: gate.reason }, { status: 403 });
    }

    const searchParams = req.nextUrl.searchParams;
    const mode = searchParams.get('mode') || 'pending';

    if (mode === 'pending') {
      const pending = await getPendingApprovals();
      return NextResponse.json({ approvals: pending });
    }

    if (mode === 'history') {
      const limit = parseInt(searchParams.get('limit') || '50', 10);
      const history = await getApprovalHistory(limit);
      return NextResponse.json({ approvals: history });
    }

    return NextResponse.json({ error: 'Invalid mode. Use "pending" or "history"' }, { status: 400 });
  } catch (error: any) {
    governor.recordFailure('approval:read');
    return NextResponse.json({ error: error.message }, { status: 500 });
  } finally {
    governor.release();
  }
}

/**
 * POST /api/approvals
 * Create a new approval request or review an existing one.
 * 
 * #40 Fix: Approval requires identity verification.
 * #41 Fix: Requires authentication.
 * #42 Fix: Feature gates checked server-side.
 * #58 Fix: ResourceGovernor — rate limited + concurrency + circuit breaker.
 */
export async function POST(req: NextRequest) {
  const user = await getAuthUser(req);
  if (!user) {
    return NextResponse.json({ error: 'Authentication required' }, { status: 401 });
  }

  // #58: Governor check (write operations for approvals are critical)
  const clientIp = req.headers.get('x-client-ip') || req.headers.get('x-forwarded-for') || 'unknown';
  const verdict = governor.check(clientIp, user.id, 'approval:write');
  if (!verdict.allowed) {
    return NextResponse.json(
      { error: verdict.reason, code: verdict.code, retryAfterMs: verdict.retryAfterMs },
      { status: 429 }
    );
  }

  try {
    const body = await req.json();
    const { operation } = body;

    // ===== CREATE APPROVAL REQUEST =====
    if (operation === 'create') {
      const { action, target, args, reason } = body;

      if (!action || !target) {
        return NextResponse.json(
          { error: 'action and target are required' },
          { status: 400 }
        );
      }

      const riskLevel = determineRiskLevel(action, target);
      
      // Check if this action actually requires approval
      const needsApproval = requiresApproval(action, target, user.role);

      if (!needsApproval) {
        return NextResponse.json({
          requiresApproval: false,
          message: 'This action does not require approval at your role level',
          riskLevel,
        });
      }

      const request = await createApprovalRequest({
        action,
        target,
        arguments: args,
        riskLevel,
        reason,
        requestedBy: user.id,
      });

      return NextResponse.json({
        requiresApproval: true,
        requestId: request.id,
        riskLevel: request.riskLevel,
        status: request.status,
        expiresAt: request.expiresAt,
        message: 'Approval request created. An admin must review and approve this action.',
      });
    }

    // ===== REVIEW APPROVAL REQUEST =====
    if (operation === 'review') {
      const { requestId, decision, reviewNote, identityToken } = body;

      if (!requestId || !decision || !identityToken) {
        return NextResponse.json(
          { error: 'requestId, decision, and identityToken are required' },
          { status: 400 }
        );
      }

      if (!['approve', 'reject'].includes(decision)) {
        return NextResponse.json(
          { error: 'decision must be "approve" or "reject"' },
          { status: 400 }
        );
      }

      // Check feature gate for approval review
      const gate = await checkFeatureGate('approval:review', user.role);
      if (!gate.allowed) {
        return NextResponse.json({ error: gate.reason }, { status: 403 });
      }

      const result = await reviewApprovalRequest({
        requestId,
        reviewerId: user.id,
        decision,
        reviewNote,
        identityToken,
        metadata: {
          ip: req.headers.get('x-forwarded-for') || req.headers.get('x-real-ip') || 'unknown',
          userAgent: req.headers.get('user-agent') || 'unknown',
        },
      });

      // Record success for circuit breaker
      governor.recordSuccess('approval:write');

      // #44-A Fix: Return the approvalToken for executing the approved action
      // This token is HMAC-signed and one-time-use — it proves the approval was granted
      return NextResponse.json({
        success: true,
        requestId: result.id,
        status: result.status,
        identityVerified: result.identityVerified,
        resolvedAt: result.resolvedAt,
        approvalToken: result.approvalToken, // #44-A: Required to execute the action
      });
    }

    // ===== CHECK IF ACTION NEEDS APPROVAL =====
    if (operation === 'check') {
      const { action, target } = body;
      if (!action || !target) {
        return NextResponse.json({ error: 'action and target are required' }, { status: 400 });
      }

      const riskLevel = determineRiskLevel(action, target);
      const needsApproval = requiresApproval(action, target, user.role);

      return NextResponse.json({
        requiresApproval: needsApproval,
        riskLevel,
        userRole: user.role,
      });
    }

    return NextResponse.json({ error: 'Invalid operation. Use "create", "review", or "check"' }, { status: 400 });
  } catch (error: any) {
    governor.recordFailure('approval:write');
    return NextResponse.json({ error: error.message }, { status: 500 });
  } finally {
    governor.release();
  }
}
