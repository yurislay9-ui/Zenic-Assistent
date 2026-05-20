// ─── Zenic-Agents v3 — Subscription Auth Helpers ──────────────────────
// INVARIANT 4: Deny-by-default authentication and authorization for
// financial endpoints. No access without verified identity.

import { NextRequest } from 'next/server';

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
 * Verifies that the request comes from an authenticated tenant.
 *
 * For the local/Termux deployment model (INVARIANT 3), this uses
 * header-based authentication with a shared secret via env var.
 *
 * If ZENIC_TENANT_SECRET is not set (development mode), all requests
 * with a valid x-tenant-id header are accepted.
 *
 * INVARIANT 4: If the secret IS set but the token doesn't match,
 * access is DENIED.
 */
export function verifyTenantAuth(req: NextRequest | Request): AuthenticatedTenant | null {
  const tenantId = extractTenantId(req);
  if (!tenantId) return null;

  // For local/Termux: validate via shared secret header
  const tenantToken = req.headers.get('x-tenant-token');
  const expectedToken = process.env.ZENIC_TENANT_SECRET;

  // If no secret configured, allow (development/offline mode per INVARIANT 3)
  if (!expectedToken) {
    return { tenantId, role: 'owner' };
  }

  // INVARIANT 4: Token mismatch = deny
  if (tenantToken !== expectedToken) return null;
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

  if (adminKey !== expectedKey) return null;

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
