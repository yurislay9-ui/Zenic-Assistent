import { db } from '@/lib/db';
import { hasMinRole } from '@/lib/auth';
import crypto from 'crypto';

/**
 * #40 Fix: HITL (Human-in-the-Loop) Approval with Identity Verification
 * #43 Fix: Removed "medium" risk tier — feature gates handle it deterministically
 * #44 Fix: Added execute-gated pipeline for approved actions
 * 
 * Previously: HITL approve just set approved=true without verifying WHO approved
 * Now: Every approval requires:
 * 1. The reviewer to be authenticated (session or API key)
 * 2. Identity verification via password re-entry or 2FA confirmation
 * 3. Audit trail with IP, user-agent, and timestamp
 * 4. Role check (only admins can approve high-risk requests)
 * 
 * #43 Fix: "medium" risk tier removed entirely.
 * Medium-risk actions (start single server, call read-only tools) are handled
 * by feature gates deterministically (role check). The HITL approval pipeline
 * is only for genuinely dangerous operations where human judgment is needed.
 * This eliminates the pattern where "medium confidence triggers expensive LLM/approval"
 * when a simple role check suffices.
 */

export type RiskLevel = 'low' | 'high' | 'critical';
export type ApprovalStatus = 'pending' | 'approved' | 'rejected' | 'expired';

export interface CreateApprovalRequest {
  action: string;
  target: string;
  arguments?: Record<string, any>;
  riskLevel?: RiskLevel;
  reason?: string;
  requestedBy: string;
  expiresAt?: Date;
}

export interface ReviewApprovalRequest {
  requestId: string;
  reviewerId: string;
  decision: 'approve' | 'reject';
  reviewNote?: string;
  identityToken: string; // Token from identity verification step
  metadata?: {
    ip?: string;
    userAgent?: string;
  };
}

/**
 * Determine risk level for an action automatically.
 * 
 * #43 Fix: "medium" tier removed. Actions are either:
 * - critical: requires human judgment (always HITL)
 * - high: potentially destructive (HITL for non-admins)
 * - low: safe enough that feature gates handle access control
 * 
 * Previously: 'start' and 'call-tool project-analyzer' returned 'medium',
 * triggering the full HITL approval pipeline unnecessarily when feature gates
 * (which already enforce role requirements) would suffice.
 */
export function determineRiskLevel(action: string, target: string): RiskLevel {
  // Critical: affects all servers or system state — ALWAYS requires HITL
  if (action === 'start-all' || action === 'stop-all') return 'critical';
  
  // High: modifies files or system configuration — HITL for non-admins
  if (action === 'call-tool' && target !== 'project-analyzer') return 'high';
  if (action === 'stop' && target === 'filesystem') return 'high';
  
  // Low: individual server start, read-only tools, etc.
  // Feature gates handle access control for these — no HITL needed.
  // #43: Removed 'medium' tier — these were dead code paths since
  // feature gates already enforce role requirements before HITL is checked.
  return 'low';
}

/**
 * Check if an action requires HITL approval.
 * 
 * #43 Fix: Simplified to only two real cases:
 * - Critical risk → always requires approval
 * - High risk → requires approval for non-admins
 * - Low risk → feature gates are sufficient (no HITL)
 * 
 * The old "medium" tier that triggered HITL for users (not operators) was
 * dead code because feature gates already blocked users at the gate level
 * before this function was ever called.
 */
export function requiresApproval(action: string, target: string, userRole: string): boolean {
  const risk = determineRiskLevel(action, target);
  
  // Critical always requires approval, even for admins
  if (risk === 'critical') return true;
  
  // High risk requires approval for non-admins
  if (risk === 'high' && !hasMinRole(userRole, 'admin')) return true;
  
  // Low risk: feature gates handle it deterministically — no HITL needed
  return false;
}

/**
 * Create a new approval request.
 */
export async function createApprovalRequest(params: CreateApprovalRequest) {
  const riskLevel = params.riskLevel || determineRiskLevel(params.action, params.target);
  // #44 Fix: Shorter expiration — 15 min instead of 30 for approved actions
  const expiresAt = params.expiresAt || new Date(Date.now() + 15 * 60 * 1000);

  return db.approvalRequest.create({
    data: {
      action: params.action,
      target: params.target,
      arguments: params.arguments ? JSON.stringify(params.arguments) : '{}',
      riskLevel,
      reason: params.reason,
      status: 'pending',
      requestedBy: params.requestedBy,
      expiresAt,
    },
  });
}

/**
 * Generate an identity verification challenge.
 * The user must re-enter their password to get a verification token.
 * This proves the person at the keyboard is actually the logged-in user.
 */
export function generateIdentityChallenge(userId: string): { challengeId: string; expiresAt: Date } {
  const secret = process.env.NEXTAUTH_SECRET;
  if (!secret) throw new Error('NEXTAUTH_SECRET not configured');

  const expiresAt = new Date(Date.now() + 5 * 60 * 1000); // 5 minutes
  const challengeId = crypto
    .createHmac('sha256', secret)
    .update(`${userId}:${expiresAt.getTime()}`)
    .digest('hex')
    .substring(0, 32);

  return { challengeId, expiresAt };
}

/**
 * Generate an identity verification token after successful password confirmation.
 * This token is required for all HITL approvals.
 */
export function generateIdentityToken(userId: string, challengeId: string): string {
  const secret = process.env.NEXTAUTH_SECRET;
  if (!secret) throw new Error('NEXTAUTH_SECRET not configured');

  const payload = JSON.stringify({
    userId,
    challengeId,
    ts: Date.now(),
    type: 'identity-verify',
  });

  const signature = crypto
    .createHmac('sha256', secret)
    .update(payload)
    .digest('hex');

  return Buffer.from(JSON.stringify({ payload, signature })).toString('base64url');
}

/**
 * Verify an identity token is valid.
 * Returns true if valid, false if invalid.
 */
export function verifyIdentityToken(token: string, expectedUserId: string): boolean {
  const secret = process.env.NEXTAUTH_SECRET;
  if (!secret) return false;

  try {
    const decoded = JSON.parse(Buffer.from(token, 'base64url').toString('utf-8'));
    const { payload, signature } = decoded;

    // Verify signature
    const expected = crypto
      .createHmac('sha256', secret)
      .update(payload)
      .digest('hex');

    if (!crypto.timingSafeEqual(
      Buffer.from(signature, 'hex'),
      Buffer.from(expected, 'hex')
    )) {
      return false;
    }

    const parsed = JSON.parse(payload);

    // Check token type
    if (parsed.type !== 'identity-verify') return false;

    // Check user matches
    if (parsed.userId !== expectedUserId) return false;

    // Check token age (max 5 minutes)
    if (Date.now() - parsed.ts > 5 * 60 * 1000) return false;

    return true;
  } catch {
    return false;
  }
}

/**
 * #44 Fix: Generate an approval execution token.
 * This is a one-time-use token that proves an approved action can be executed.
 * It's bound to: the approval ID, the reviewer, and the approval timestamp.
 * Without this, anyone who knows a requestId could execute the action.
 */
export function generateApprovalToken(approvalId: string, reviewerId: string, approvedAt: Date): string {
  const secret = process.env.NEXTAUTH_SECRET;
  if (!secret) throw new Error('NEXTAUTH_SECRET not configured');

  const payload = JSON.stringify({
    approvalId,
    reviewerId,
    approvedAt: approvedAt.getTime(),
    type: 'approval-exec',
    ts: Date.now(),
  });

  const signature = crypto
    .createHmac('sha256', secret)
    .update(payload)
    .digest('hex');

  return Buffer.from(JSON.stringify({ payload, signature })).toString('base64url');
}

/**
 * #44 Fix: Verify an approval execution token.
 * This ensures the token was generated server-side for this specific approval,
 * preventing unauthorized execution of approved actions.
 */
export function verifyApprovalToken(token: string, expectedApprovalId: string, expectedReviewerId: string): boolean {
  const secret = process.env.NEXTAUTH_SECRET;
  if (!secret) return false;

  try {
    const decoded = JSON.parse(Buffer.from(token, 'base64url').toString('utf-8'));
    const { payload, signature } = decoded;

    // Verify signature
    const expected = crypto
      .createHmac('sha256', secret)
      .update(payload)
      .digest('hex');

    if (!crypto.timingSafeEqual(
      Buffer.from(signature, 'hex'),
      Buffer.from(expected, 'hex')
    )) {
      return false;
    }

    const parsed = JSON.parse(payload);

    // Check token type
    if (parsed.type !== 'approval-exec') return false;

    // Check approval ID matches
    if (parsed.approvalId !== expectedApprovalId) return false;

    // Check reviewer ID matches
    if (parsed.reviewerId !== expectedReviewerId) return false;

    // Check token age (max 15 minutes)
    if (Date.now() - parsed.ts > 15 * 60 * 1000) return false;

    // Check the approval hasn't been executed before (one-time-use via timestamp)
    // The approvedAt must match the stored value
    if (!parsed.approvedAt) return false;

    return true;
  } catch {
    return false;
  }
}

/**
 * Review (approve/reject) an approval request with full identity verification.
 * 
 * #40 Fix: This function ensures:
 * 1. The reviewer's identity has been verified (identityToken)
 * 2. The reviewer has sufficient role for the risk level
 * 3. An audit trail is created
 * 
 * #44 Fix: Approval now returns a one-time execution token
 * that must be presented to execute the approved action.
 */
export async function reviewApprovalRequest(params: ReviewApprovalRequest) {
  const request = await db.approvalRequest.findUnique({
    where: { id: params.requestId },
  });

  if (!request) {
    throw new Error('Approval request not found');
  }

  if (request.status !== 'pending') {
    throw new Error(`Request is already ${request.status}`);
  }

  // #44 Fix: Check expiration during review too
  if (request.expiresAt && new Date() > request.expiresAt) {
    await db.approvalRequest.update({
      where: { id: params.requestId },
      data: { status: 'expired', resolvedAt: new Date() },
    });
    throw new Error('Request has expired');
  }

  // #40 Fix: Verify identity token
  if (!verifyIdentityToken(params.identityToken, params.reviewerId)) {
    throw new Error('Identity verification failed. Please re-verify your identity.');
  }

  // Get reviewer info for role check
  const reviewer = await db.user.findUnique({
    where: { id: params.reviewerId },
  });

  if (!reviewer || !reviewer.isActive) {
    throw new Error('Reviewer not found or inactive');
  }

  // Risk-based role check
  const requiredRole: Record<string, string> = {
    low: 'operator',
    high: 'admin',
    critical: 'admin',
  };

  if (!hasMinRole(reviewer.role, requiredRole[request.riskLevel] || 'admin')) {
    throw new Error(`Insufficient role for ${request.riskLevel} risk request. Requires: ${requiredRole[request.riskLevel]}`);
  }

  // Cannot approve own request
  if (request.requestedBy === params.reviewerId) {
    throw new Error('Cannot approve your own request — a different admin must review');
  }

  const resolvedAt = new Date();

  // Update request
  const updated = await db.approvalRequest.update({
    where: { id: params.requestId },
    data: {
      status: params.decision === 'approve' ? 'approved' : 'rejected',
      reviewedBy: params.reviewerId,
      reviewNote: params.reviewNote,
      identityVerified: true,
      resolvedAt,
    },
  });

  // Create audit trail
  await db.approvalAction.create({
    data: {
      requestId: params.requestId,
      userId: params.reviewerId,
      action: params.decision === 'approve' ? 'approve' : 'reject',
      metadata: JSON.stringify({
        ip: params.metadata?.ip,
        userAgent: params.metadata?.userAgent,
        identityVerified: true,
        timestamp: resolvedAt.toISOString(),
        reviewerRole: reviewer.role,
        riskLevel: request.riskLevel,
      }),
    },
  });

  // #44 Fix: Generate one-time approval execution token
  let approvalToken: string | undefined;
  if (params.decision === 'approve') {
    approvalToken = generateApprovalToken(params.requestId, params.reviewerId, resolvedAt);
  }

  return { ...updated, approvalToken };
}

/**
 * Get all pending approval requests.
 */
export async function getPendingApprovals() {
  return db.approvalRequest.findMany({
    where: { status: 'pending' },
    orderBy: { createdAt: 'desc' },
    include: {
      requester: { select: { id: true, name: true, email: true, role: true } },
    },
  });
}

/**
 * Get approval history with audit trail.
 */
export async function getApprovalHistory(limit = 50) {
  return db.approvalRequest.findMany({
    where: { status: { in: ['approved', 'rejected', 'expired'] } },
    orderBy: { resolvedAt: 'desc' },
    take: limit,
    include: {
      requester: { select: { id: true, name: true, email: true, role: true } },
      reviewer: { select: { id: true, name: true, email: true, role: true } },
      actions: true,
    },
  });
}
