import { db } from '@/lib/db';
import { hasMinRole } from '@/lib/auth';
import crypto from 'crypto';

/**
 * #42 Fix: Feature Gate System
 * 
 * Feature gates are stored in the database and verified server-side.
 * They CANNOT be spoofed via headers because:
 * 1. The gate check reads from DB, not from request headers
 * 2. Feature access requires a signed token (HMAC) generated server-side
 * 3. The minimum role requirement is enforced server-side
 * 
 * Previously: Feature gates were checked via x-feature-enabled header (spoofable)
 * Now: Feature gates require DB lookup + role verification + signed token
 */

export interface FeatureGateCheck {
  allowed: boolean;
  reason: string;
  requireApproval: boolean;
  gate?: {
    key: string;
    name: string;
    minRole: string;
    requireApproval: boolean;
  };
}

/**
 * Check if a feature gate allows the given action for the given role.
 * All checks are server-side — no header-based spoofing possible.
 */
export async function checkFeatureGate(
  featureKey: string,
  userRole: string
): Promise<FeatureGateCheck> {
  const gate = await db.featureGate.findUnique({
    where: { key: featureKey },
  });

  if (!gate) {
    // If gate doesn't exist, default to admin-only (secure by default)
    return {
      allowed: hasMinRole(userRole, 'admin'),
      reason: gate ? 'Feature gate not configured' : 'Unknown feature — admin only by default',
      requireApproval: false,
    };
  }

  if (!gate.enabled) {
    return {
      allowed: false,
      reason: `Feature "${gate.name}" is currently disabled`,
      requireApproval: false,
      gate: { key: gate.key, name: gate.name, minRole: gate.minRole, requireApproval: gate.requireApproval },
    };
  }

  if (!hasMinRole(userRole, gate.minRole)) {
    return {
      allowed: false,
      reason: `Feature "${gate.name}" requires role "${gate.minRole}" or higher (current: "${userRole}")`,
      requireApproval: false,
      gate: { key: gate.key, name: gate.name, minRole: gate.minRole, requireApproval: gate.requireApproval },
    };
  }

  return {
    allowed: true,
    reason: 'Access granted',
    requireApproval: gate.requireApproval,
    gate: { key: gate.key, name: gate.name, minRole: gate.minRole, requireApproval: gate.requireApproval },
  };
}

/**
 * Generate a tamper-proof feature token.
 * This token proves the server authorized access to a specific feature.
 * It includes: feature key, user role, timestamp, and HMAC signature.
 * 
 * This replaces header-based feature flags which could be spoofed.
 */
export function generateFeatureToken(featureKey: string, userRole: string): string {
  const secret = process.env.NEXTAUTH_SECRET;
  if (!secret) throw new Error('NEXTAUTH_SECRET not configured');

  const payload = JSON.stringify({
    feature: featureKey,
    role: userRole,
    ts: Date.now(),
  });

  const signature = crypto
    .createHmac('sha256', secret)
    .update(payload)
    .digest('hex');

  // Token = base64(payload).signature
  const tokenPayload = Buffer.from(payload).toString('base64url');
  return `${tokenPayload}.${signature}`;
}

/**
 * Verify a feature token is valid and not tampered with.
 * Returns the parsed payload if valid, null if invalid.
 */
export function verifyFeatureToken(token: string): { feature: string; role: string; ts: number } | null {
  const secret = process.env.NEXTAUTH_SECRET;
  if (!secret) return null;

  const [payloadB64, signature] = token.split('.');
  if (!payloadB64 || !signature) return null;

  try {
    const payload = Buffer.from(payloadB64, 'base64url').toString('utf-8');
    
    // Verify signature
    const expected = crypto
      .createHmac('sha256', secret)
      .update(payload)
      .digest('hex');

    if (!crypto.timingSafeEqual(
      Buffer.from(signature, 'hex'),
      Buffer.from(expected, 'hex')
    )) {
      return null; // Signature mismatch — token was tampered with
    }

    const parsed = JSON.parse(payload);

    // Check token age (max 10 minutes)
    if (Date.now() - parsed.ts > 10 * 60 * 1000) {
      return null; // Token expired
    }

    return parsed;
  } catch {
    return null;
  }
}

/**
 * Seed default feature gates into the database.
 */
export async function seedFeatureGates(): Promise<void> {
  const defaultGates = [
    {
      key: 'mcp:list',
      name: 'List MCP Servers',
      description: 'View registered MCP servers and their status',
      enabled: true,
      minRole: 'user',
      requireApproval: false,
    },
    {
      key: 'mcp:health',
      name: 'Health Check',
      description: 'Check API health status',
      enabled: true,
      minRole: 'user',
      requireApproval: false,
    },
    {
      key: 'mcp:start',
      name: 'Start MCP Server',
      description: 'Start an individual MCP server',
      enabled: true,
      minRole: 'operator',
      requireApproval: false,
    },
    {
      key: 'mcp:stop',
      name: 'Stop MCP Server',
      description: 'Stop an individual MCP server',
      enabled: true,
      minRole: 'operator',
      requireApproval: false,
    },
    {
      key: 'mcp:start-all',
      name: 'Start All Servers',
      description: 'Start all registered MCP servers at once',
      enabled: true,
      minRole: 'admin',
      requireApproval: true,
    },
    {
      key: 'mcp:stop-all',
      name: 'Stop All Servers',
      description: 'Stop all running MCP servers at once',
      enabled: true,
      minRole: 'admin',
      requireApproval: true,
    },
    {
      key: 'mcp:call-tool',
      name: 'Call MCP Tool',
      description: 'Execute a tool on an MCP server',
      enabled: true,
      minRole: 'operator',
      requireApproval: false,
    },
    {
      key: 'mcp:call-tool-dangerous',
      name: 'Call Dangerous Tool',
      description: 'Execute tools that modify files or system state',
      enabled: true,
      minRole: 'admin',
      requireApproval: true,
    },
    {
      key: 'approval:list',
      name: 'View Approval Requests',
      description: 'View pending HITL approval requests',
      enabled: true,
      minRole: 'operator',
      requireApproval: false,
    },
    {
      key: 'approval:review',
      name: 'Review Approvals',
      description: 'Approve or reject HITL approval requests with identity verification',
      enabled: true,
      minRole: 'admin',
      requireApproval: false,
    },
  ];

  for (const gate of defaultGates) {
    await db.featureGate.upsert({
      where: { key: gate.key },
      update: { name: gate.name, description: gate.description },
      create: gate,
    });
  }
}
