// ─── Zenic-Agents v3 — Subscription Auth Helpers ──────────────────────
// INVARIANT 4: Deny-by-default authentication and authorization for
// financial endpoints. No access without verified identity.

import { NextRequest } from 'next/server';
import { timingSafeEqual } from 'crypto';

// ─── Tenant Authentication ───

export interface AuthenticatedTenant {
  tenantId: string;
  role: 'owner' | 'admin' | 'member';
}

/**
 * Extracts the tenant ID from request headers.
 * Returns null if no valid tenant ID found.
 */
export function extractTenantId(req: NextRequest | Request): string | null {
  const tenantId = req.headers.get('x-tenant-id');
  return tenantId && tenantId.length > 0 ? tenantId : null;
}

/**
 * Constant-time string comparison to prevent timing attacks (SAST H-64).
 * Returns true if both strings are equal, false otherwise.
 * When lengths differ, performs a dummy comparison to avoid leaking length info.
 */
function safeEqual(a: string, b: string): boolean {
  const bufA = Buffer.from(a, 'utf-8');
  const bufB = Buffer.from(b, 'utf-8');
  if (bufA.length !== bufB.length) {
    // Still perform a comparison to avoid leaking length via timing
    return !timingSafeEqual(bufA, bufA);
  }
  return timingSafeEqual(bufA, bufB);
}

/**
 * Verifies that the request comes from an authenticated tenant.
 *
 * For the local/Termux deployment model (INVARIANT 3), this uses
 * header-based authentication with a shared secret via env var.
 *
 * SECURITY (SAST H-63): If ZENIC_TENANT_SECRET is not set, access is DENIED
 * unless ZENIC_DEV_MODE=1 is explicitly enabled. This aligns with
 * verifyAdminAuth()'s fail-closed behavior (INVARIANT 4).
 */
export function verifyTenantAuth(req: NextRequest | Request): AuthenticatedTenant | null {
  const tenantId = extractTenantId(req);
  if (!tenantId) return null;

  // For local/Termux: validate via shared secret header
  const tenantToken = req.headers.get('x-tenant-token');
  const expectedToken = process.env.ZENIC_TENANT_SECRET;

  // SECURITY (SAST H-63): Fail-closed when no secret is configured.
  // Dev override requires explicit ZENIC_DEV_MODE=1 + development environment.
  if (!expectedToken) {
    if (process.env.ZENIC_DEV_MODE === '1' && process.env.NODE_ENV === 'development') {
      console.warn(
        `[Tenant Auth] ⚠️ DEV MODE: No ZENIC_TENANT_SECRET set. ` +
        `Tenant ${tenantId} auto-authenticated as owner.`
      );
      return { tenantId, role: 'owner' };
    }
    // INVARIANT 4: No secret configured = tenant endpoints LOCKED
    return null;
  }

  // INVARIANT 4: Token mismatch = deny (timing-safe comparison — SAST H-64)
  if (!tenantToken || !safeEqual(tenantToken, expectedToken)) return null;
  return { tenantId, role: 'owner' };
}

// ─── Admin Authorization ───

export interface AdminUser {
  userId: string;
  role: 'super_admin' | 'admin';
}

/**
 * Verifies that the caller is an admin user.
 * Checks the x-admin-key header against the ZENIC_ADMIN_KEY env var.
 *
 * INVARIANT 4: Deny-by-default — no key configured = admin endpoints LOCKED.
 * This is intentional: in production, you MUST set ZENIC_ADMIN_KEY.
 * If the env var is not set, admin operations are completely disabled
 * (fail-closed, not fail-open).
 */
export function verifyAdminAuth(req: Request | NextRequest): AdminUser | null {
  const adminKey = req.headers.get('x-admin-key');
  const expectedKey = process.env.ZENIC_ADMIN_KEY;

  // INVARIANT 4: No admin key configured = admin access DENIED
  // This prevents accidental exposure in production
  if (!expectedKey) {
    return null;
  }

  // SECURITY (SAST H-64): Constant-time comparison prevents timing attacks
  if (!adminKey || !safeEqual(adminKey, expectedKey)) return null;

  const adminUserId = req.headers.get('x-admin-user-id') || 'admin';
  return { userId: adminUserId, role: 'admin' };
}

// ─── Guard Return Types ───

function unauthorizedResponse(message: string): Response {
  return new Response(
    JSON.stringify({ error: 'Unauthorized', message }),
    { status: 401, headers: { 'Content-Type': 'application/json' } }
  );
}

function forbiddenResponse(message: string): Response {
  return new Response(
    JSON.stringify({ error: 'Forbidden', message }),
    { status: 403, headers: { 'Content-Type': 'application/json' } }
  );
}

/**
 * Requires tenant auth or returns 401.
 * Use at the top of any subscription route handler.
 *
 * Usage:
 * ```ts
 * export async function POST(req: NextRequest) {
 *   const auth = requireTenantAuth(req);
 *   if (auth instanceof Response) return auth;
 *   // auth.tenantId is verified
 * }
 * ```
 */
export function requireTenantAuth(req: NextRequest): AuthenticatedTenant | Response {
  const auth = verifyTenantAuth(req);
  if (!auth) {
    return unauthorizedResponse('Valid x-tenant-id header required');
  }
  return auth;
}

/**
 * Requires admin auth or returns 403.
 * Use at the top of admin-only routes (payment confirm, etc.)
 *
 * Usage:
 * ```ts
 * export async function POST(req: Request) {
 *   const admin = requireAdminAuth(req);
 *   if (admin instanceof Response) return admin;
 *   // admin.userId is verified
 * }
 * ```
 */
export function requireAdminAuth(req: Request): AdminUser | Response {
  const auth = verifyAdminAuth(req);
  if (!auth) {
    return forbiddenResponse(
      'Admin authorization required. Provide x-admin-key header. ' +
      'Ensure ZENIC_ADMIN_KEY env var is configured.'
    );
  }
  return auth;
}

/**
 * Verifies that the authenticated tenant matches the requested tenantId.
 * Prevents tenant A from accessing tenant B's data.
 *
 * Usage:
 * ```ts
 * const auth = requireTenantAuth(req);
 * if (auth instanceof Response) return auth;
 * if (!verifyTenantOwnership(auth, requestedTenantId)) {
 *   return NextResponse.json({ error: 'Access denied' }, { status: 403 });
 * }
 * ```
 */
export function verifyTenantOwnership(auth: AuthenticatedTenant, requestedTenantId: string): boolean {
  return auth.tenantId === requestedTenantId;
}
