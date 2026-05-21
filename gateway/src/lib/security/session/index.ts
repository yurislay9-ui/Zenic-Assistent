// ─── Zenic-Agents Gateway — Session Management Module ─────────────────
// Provides in-memory session lifecycle management layered on top of the
// existing header-based auth (X-User-Id). Sessions add stateful tracking
// of authenticated users with expiry, revocation, rotation, and per-user
// session limits.
//
// INVARIANT 4: La regla DENY es absoluta. Expired or revoked sessions
// are never treated as valid. All validation checks are fail-closed.

import { randomUUID } from 'crypto';
import { NextResponse } from 'next/server';

// ─── Type Definitions ───────────────────────────────────────────────

/**
 * Optional metadata attached to a session at creation time.
 *
 * Used to record contextual information about the client and the
 * authentication context that produced the session. All fields are
 * optional to accommodate different auth flows.
 */
export interface SessionMetadata {
  /** Client IP address, forwarded by the proxy / load balancer */
  ipAddress?: string;
  /** Client User-Agent string */
  userAgent?: string;
  /** Role assigned to the user at session-creation time */
  role?: string;
  /** Tenant ID the user belongs to (multi-tenancy) */
  tenantId?: string;
}

/**
 * Represents an active (or revoked) user session.
 *
 * Instances are created by {@link SessionManager.createSession} and stored
 * in memory. A session is considered **valid** when all of the following
 * hold:
 * - `isRevoked` is `false`
 * - `expiresAt` is in the future (relative to `Date.now()`)
 *
 * @example
 * ```ts
 * const session: Session = {
 *   sessionId: '550e8400-e29b-41d4-a716-446655440000',
 *   userId: 'user_42',
 *   createdAt: 1710000000000,
 *   lastActivityAt: 1710000000000,
 *   expiresAt: 1710001800000,
 *   isRevoked: false,
 *   metadata: { role: 'operator', tenantId: 'tenant_abc' },
 * };
 * ```
 */
export interface Session {
  /** Unique session identifier (UUID v4) */
  sessionId: string;
  /** ID of the user this session belongs to */
  userId: string;
  /** Epoch timestamp (ms) when the session was created */
  createdAt: number;
  /** Epoch timestamp (ms) of the last session activity / validation */
  lastActivityAt: number;
  /** Epoch timestamp (ms) when the session expires */
  expiresAt: number;
  /** Whether this session has been explicitly revoked */
  isRevoked: boolean;
  /** Optional metadata captured at session-creation time */
  metadata: SessionMetadata;
}

/**
 * Configuration options that control session lifecycle behaviour.
 *
 * Pass a partial object to {@link SessionManager.configure} or to
 * {@link withSessionValidation} to override defaults.
 *
 * @example
 * ```ts
 * const config: SessionConfig = {
 *   sessionTimeoutMs: 60 * 60 * 1000,  // 1 hour
 *   maxSessionsPerUser: 10,
 *   renewalThresholdMs: 10 * 60 * 1000, // 10 min before expiry
 *   enableRotation: true,
 * };
 * ```
 */
export interface SessionConfig {
  /** Absolute session lifetime in milliseconds (default: 30 min) */
  sessionTimeoutMs: number;
  /** Maximum concurrent active sessions per user (default: 5) */
  maxSessionsPerUser: number;
  /**
   * How many milliseconds before expiry a session is eligible for
   * automatic renewal during validation (default: 5 min).
   *
   * When `enableRotation` is `true` and the remaining time until
   * `expiresAt` is less than or equal to this threshold, the session
   * will be automatically refreshed.
   */
  renewalThresholdMs: number;
  /**
   * Whether to automatically rotate (extend) sessions that fall within
   * the renewal threshold during validation (default: `true`).
   */
  enableRotation: boolean;
}

/**
 * Default configuration values used when no overrides are provided.
 */
export const DEFAULT_SESSION_CONFIG: SessionConfig = {
  sessionTimeoutMs: 30 * 60 * 1000,   // 30 minutes
  maxSessionsPerUser: 5,
  renewalThresholdMs: 5 * 60 * 1000,  // 5 minutes before expiry
  enableRotation: true,
};

// ─── SessionManager (Singleton) ─────────────────────────────────────

/**
 * Central session lifecycle manager for the Zenic-Agents gateway.
 *
 * Implements the **Singleton** pattern — use {@link getSessionManager}
 * to obtain the shared instance.
 *
 * Sessions are stored **in-memory** using a `Map<string, Session>`. This
 * is intentionally simple: for a single-process gateway the overhead of
 * an external session store is unnecessary. If the gateway later needs
 * to run across multiple processes, the storage layer can be swapped out
 * without changing the public API.
 *
 * **Thread-safety note:** Node.js is single-threaded, so concurrent
 * access to the internal maps is safe as long as the caller does not
 * `await` between a read and a write that must be atomic. All public
 * methods are synchronous for this reason.
 */
export class SessionManager {
  private static instance: SessionManager | null = null;

  /** Active sessions keyed by session ID */
  private sessions: Map<string, Session> = new Map();

  /** Index: user ID → set of session IDs (for fast user-session lookup) */
  private userSessionsIndex: Map<string, Set<string>> = new Map();

  /** Current configuration (merged with defaults) */
  private config: SessionConfig = { ...DEFAULT_SESSION_CONFIG };

  /** Private to enforce singleton access via {@link getSessionManager}. */
  private constructor() {}

  /**
   * Returns the singleton {@link SessionManager} instance, creating it on
   * first access.
   *
   * @example
   * ```ts
   * const manager = getSessionManager();
   * const session = manager.createSession('user_42');
   * ```
   */
  public static getInstance(): SessionManager {
    if (!SessionManager.instance) {
      SessionManager.instance = new SessionManager();
    }
    return SessionManager.instance;
  }

  /**
   * Reset the singleton and clear all sessions (useful for testing).
   *
   * @internal
   */
  public static resetInstance(): void {
    if (SessionManager.instance) {
      SessionManager.instance.sessions.clear();
      SessionManager.instance.userSessionsIndex.clear();
    }
    SessionManager.instance = null;
  }

  /**
   * Update the session manager configuration.
   *
   * Merges the provided partial config with the current config (which
   * starts as {@link DEFAULT_SESSION_CONFIG}). Only the supplied keys
   * are overridden.
   *
   * @param config - Partial configuration to merge.
   *
   * @example
   * ```ts
   * getSessionManager().configure({ sessionTimeoutMs: 60 * 60 * 1000 });
   * ```
   */
  public configure(config: Partial<SessionConfig>): void {
    this.config = { ...this.config, ...config };
  }

  /**
   * Return the current effective configuration.
   *
   * @returns A copy of the active {@link SessionConfig}.
   */
  public getConfig(): SessionConfig {
    return { ...this.config };
  }

  // ── Session lifecycle ───────────────────────────────────────────

  /**
   * Create a new session for the given user.
   *
   * If the user already has `maxSessionsPerUser` active sessions, the
   * **oldest** active session is automatically revoked before the new
   * one is created (FIFO eviction).
   *
   * @param userId   - ID of the user to create a session for.
   * @param metadata - Optional client / auth context metadata.
   * @returns The newly created {@link Session}.
   *
   * @example
   * ```ts
   * const session = manager.createSession('user_42', {
   *   ipAddress: '10.0.0.1',
   *   userAgent: 'Mozilla/5.0',
   *   role: 'operator',
   *   tenantId: 'tenant_abc',
   * });
   * console.log(session.sessionId); // UUID
   * ```
   */
  public createSession(userId: string, metadata?: SessionMetadata): Session {
    const now = Date.now();

    // Enforce per-user session limit by evicting the oldest session
    const userSessionIds = this.userSessionsIndex.get(userId);
    if (userSessionIds && userSessionIds.size >= this.config.maxSessionsPerUser) {
      // Find the oldest non-revoked session for this user
      let oldestSession: Session | null = null;
      for (const sid of userSessionIds) {
        const s = this.sessions.get(sid);
        if (s && !s.isRevoked) {
          if (!oldestSession || s.createdAt < oldestSession.createdAt) {
            oldestSession = s;
          }
        }
      }
      if (oldestSession) {
        this.revokeSession(oldestSession.sessionId);
      }
    }

    const session: Session = {
      sessionId: randomUUID(),
      userId,
      createdAt: now,
      lastActivityAt: now,
      expiresAt: now + this.config.sessionTimeoutMs,
      isRevoked: false,
      metadata: metadata ?? {},
    };

    // Store session
    this.sessions.set(session.sessionId, session);

    // Update user-sessions index
    if (!this.userSessionsIndex.has(userId)) {
      this.userSessionsIndex.set(userId, new Set());
    }
    this.userSessionsIndex.get(userId)!.add(session.sessionId);

    return session;
  }

  /**
   * Validate a session by its ID.
   *
   * A session is considered **valid** when:
   * - It exists in the session store
   * - `isRevoked` is `false`
   * - `expiresAt` is in the future
   *
   * If the session is valid and falls within the renewal threshold
   * (and rotation is enabled), it will be automatically refreshed.
   *
   * @param sessionId - The session ID to validate.
   * @returns The valid {@link Session} if all checks pass, or `null`
   *          if the session is missing, expired, or revoked.
   *
   * @example
   * ```ts
   * const session = manager.validateSession('550e8400-...');
   * if (session) {
   *   // Session is valid — proceed
   * } else {
   *   // Session invalid — return 401
   * }
   * ```
   */
  public validateSession(sessionId: string): Session | null {
    const session = this.sessions.get(sessionId);
    if (!session) {
      return null;
    }

    // Check revocation
    if (session.isRevoked) {
      return null;
    }

    // Check expiry
    const now = Date.now();
    if (now >= session.expiresAt) {
      return null;
    }

    // Update last activity timestamp
    session.lastActivityAt = now;

    // Auto-refresh if within renewal threshold and rotation is enabled
    if (this.config.enableRotation) {
      const remainingMs = session.expiresAt - now;
      if (remainingMs <= this.config.renewalThresholdMs) {
        session.expiresAt = now + this.config.sessionTimeoutMs;
      }
    }

    return session;
  }

  /**
   * Revoke a session by its ID.
   *
   * Revoked sessions will fail all future validation checks. This
   * operation is **idempotent** — revoking an already-revoked or
   * non-existent session returns `false` without side effects.
   *
   * @param sessionId - The session ID to revoke.
   * @returns `true` if the session was active and is now revoked;
   *          `false` if the session was not found or already revoked.
   *
   * @example
   * ```ts
   * const revoked = manager.revokeSession('550e8400-...');
   * // revoked === true  — session was active, now revoked
   * // revoked === false — session didn't exist or was already revoked
   * ```
   */
  public revokeSession(sessionId: string): boolean {
    const session = this.sessions.get(sessionId);
    if (!session || session.isRevoked) {
      return false;
    }

    session.isRevoked = true;
    return true;
  }

  /**
   * Refresh (extend) a session's expiry time.
   *
   * This is an **explicit** refresh — it extends the session regardless
   * of the renewal threshold. This is useful for user-driven "remember
   * me" flows or long-lived operations that need to keep the session
   * alive.
   *
   * Only valid (non-expired, non-revoked) sessions can be refreshed.
   *
   * @param sessionId - The session ID to refresh.
   * @returns The refreshed {@link Session} with updated `expiresAt` and
   *          `lastActivityAt`, or `null` if the session is invalid.
   *
   * @example
   * ```ts
   * const refreshed = manager.refreshSession('550e8400-...');
   * if (refreshed) {
   *   console.log('New expiry:', new Date(refreshed.expiresAt));
   * }
   * ```
   */
  public refreshSession(sessionId: string): Session | null {
    const session = this.sessions.get(sessionId);
    if (!session) {
      return null;
    }

    // Cannot refresh revoked or expired sessions
    if (session.isRevoked) {
      return null;
    }

    const now = Date.now();
    if (now >= session.expiresAt) {
      return null;
    }

    session.expiresAt = now + this.config.sessionTimeoutMs;
    session.lastActivityAt = now;

    return session;
  }

  /**
   * Get all **active** (non-expired, non-revoked) sessions for a user.
   *
   * @param userId - The user ID to look up sessions for.
   * @returns An array of active {@link Session} objects. Returns an
   *          empty array if the user has no active sessions.
   *
   * @example
   * ```ts
   * const sessions = manager.getSessionByUserId('user_42');
   * console.log(`Active sessions: ${sessions.length}`);
   * ```
   */
  public getSessionByUserId(userId: string): Session[] {
    const sessionIds = this.userSessionsIndex.get(userId);
    if (!sessionIds) {
      return [];
    }

    const now = Date.now();
    const activeSessions: Session[] = [];

    for (const sid of sessionIds) {
      const session = this.sessions.get(sid);
      if (session && !session.isRevoked && now < session.expiresAt) {
        activeSessions.push(session);
      }
    }

    return activeSessions;
  }

  /**
   * Revoke **all** sessions for a given user.
   *
   * Typically used during security-sensitive operations like password
   * resets, account lockouts, or administrative user suspension.
   *
   * @param userId - The user whose sessions should be revoked.
   * @returns The number of sessions that were actually revoked (i.e.
   *          were active before this call).
   *
   * @example
   * ```ts
   * // Password reset — force re-login on all devices
   * const revokedCount = manager.revokeAllUserSessions('user_42');
   * console.log(`Revoked ${revokedCount} sessions`);
   * ```
   */
  public revokeAllUserSessions(userId: string): number {
    const sessionIds = this.userSessionsIndex.get(userId);
    if (!sessionIds) {
      return 0;
    }

    let revokedCount = 0;
    for (const sid of sessionIds) {
      const session = this.sessions.get(sid);
      if (session && !session.isRevoked) {
        session.isRevoked = true;
        revokedCount++;
      }
    }

    return revokedCount;
  }

  /**
   * Remove all expired sessions from memory.
   *
   * This purges sessions whose `expiresAt` is in the past, freeing
   * memory. Revoked sessions that have also expired are also cleaned
   * up. Running this periodically (e.g. every 10 minutes) prevents
   * unbounded memory growth in long-running processes.
   *
   * @returns The number of sessions removed from memory.
   *
   * @example
   * ```ts
   * // Run on a timer
   * setInterval(() => {
   *   const removed = manager.cleanupExpiredSessions();
   *   if (removed > 0) {
   *     console.log(`Cleaned up ${removed} expired sessions`);
   *   }
   * }, 10 * 60 * 1000);
   * ```
   */
  public cleanupExpiredSessions(): number {
    const now = Date.now();
    let removedCount = 0;

    for (const [sid, session] of this.sessions) {
      if (now >= session.expiresAt) {
        // Remove from sessions map
        this.sessions.delete(sid);

        // Remove from user-sessions index
        const userIdSet = this.userSessionsIndex.get(session.userId);
        if (userIdSet) {
          userIdSet.delete(sid);
          // Clean up empty sets to avoid memory leaks
          if (userIdSet.size === 0) {
            this.userSessionsIndex.delete(session.userId);
          }
        }

        removedCount++;
      }
    }

    return removedCount;
  }

  // ── Diagnostic helpers ──────────────────────────────────────────

  /**
   * Get the total number of sessions currently in memory (including
   * expired and revoked ones that haven't been cleaned up yet).
   *
   * @returns Total session count.
   */
  public get totalSessions(): number {
    return this.sessions.size;
  }

  /**
   * Get the number of **active** (non-expired, non-revoked) sessions.
   *
   * @returns Active session count.
   */
  public get activeSessionCount(): number {
    const now = Date.now();
    let count = 0;
    for (const session of this.sessions.values()) {
      if (!session.isRevoked && now < session.expiresAt) {
        count++;
      }
    }
    return count;
  }
}

// ─── Singleton Access ───────────────────────────────────────────────

/**
 * Returns the shared {@link SessionManager} singleton.
 *
 * This is the primary way to access session management throughout the
 * gateway. The first call creates the instance; subsequent calls return
 * the same instance.
 *
 * @returns The singleton {@link SessionManager}.
 *
 * @example
 * ```ts
 * import { getSessionManager } from '@/lib/security/session';
 *
 * const manager = getSessionManager();
 * const session = manager.createSession('user_42');
 * ```
 */
export function getSessionManager(): SessionManager {
  return SessionManager.getInstance();
}

// ─── Middleware: withSessionValidation ───────────────────────────────

/**
 * Type for a standard route handler function compatible with Next.js
 * API routes or Express-style middleware.
 *
 * The request object is extended with session information injected by
 * {@link withSessionValidation}.
 */
type SessionRouteHandler = (
  req: Request & {
    /** Authenticated user ID (from session, not from X-User-Id header) */
    userId?: string;
    /** Client IP extracted by the proxy / load balancer */
    ip?: string;
    /** Extracted correlation / trace ID */
    correlationId?: string;
    /** Validated session object, injected by session middleware */
    session?: Session;
  },
  ctx?: Record<string, unknown>
) => Promise<Response> | Response;

/**
 * Extract the session ID from an incoming request.
 *
 * Looks in two places (in order of precedence):
 * 1. `Authorization: Bearer <sessionId>` header
 * 2. `X-Session-Id` header
 *
 * @param req - The incoming request.
 * @returns The session ID string, or `null` if neither header is present.
 */
function extractSessionId(req: Request): string | null {
  // Try Authorization: Bearer <token>
  const authHeader = req.headers.get('authorization');
  if (authHeader) {
    const parts = authHeader.split(' ');
    if (parts.length === 2 && parts[0].toLowerCase() === 'bearer') {
      return parts[1].trim() || null;
    }
  }

  // Fall back to X-Session-Id header
  const sessionId = req.headers.get('x-session-id');
  return sessionId?.trim() || null;
}

/**
 * Middleware wrapper that enforces session validation on a route handler.
 *
 * **Validation flow:**
 * 1. Extracts the session ID from the `Authorization: Bearer` header or
 *    the `X-Session-Id` header.
 * 2. Validates the session via {@link SessionManager.validateSession}
 *    (checks existence, expiry, and revocation).
 * 3. If the session is within the renewal threshold and rotation is
 *    enabled, it is automatically refreshed.
 * 4. On success, injects session info into the request object
 *    (`req.session`, `req.userId`) and calls the wrapped handler.
 * 5. On failure, returns a `401 Unauthorized` JSON response.
 *
 * **Integration with existing header-based auth:**
 * This middleware layers **on top of** the existing `X-User-Id` auth.
 * If a valid session is found, `req.userId` is set from the session's
 * `userId` field, overriding any `X-User-Id` header. This allows a
 * gradual migration path: routes can adopt session validation one at a
 * time without breaking existing header-based auth on other routes.
 *
 * @param handler - The original route handler to wrap.
 * @param config  - Optional partial {@link SessionConfig} to override
 *                  defaults for the session manager (applied once).
 * @returns A wrapped handler with session validation.
 *
 * @example
 * ```ts
 * // Next.js App Router API route
 * export const GET = withSessionValidation(async (req) => {
 *   const session = req.session;
 *   console.log(`User ${session?.userId} accessed resource`);
 *   return Response.json({ data: 'protected' });
 * });
 * ```
 *
 * @example
 * ```ts
 * // With custom config
 * export const POST = withSessionValidation(
 *   async (req) => {
 *     // ... handler logic
 *     return Response.json({ ok: true });
 *   },
 *   { sessionTimeoutMs: 60 * 60 * 1000 },  // 1-hour sessions
 * );
 * ```
 */
export function withSessionValidation(
  handler: SessionRouteHandler,
  config?: Partial<SessionConfig>
): SessionRouteHandler {
  const manager = getSessionManager();

  // Apply custom config if provided
  if (config) {
    manager.configure(config);
  }

  return async (req, ctx) => {
    // 1. Extract session ID
    const sessionId = extractSessionId(req);

    if (!sessionId) {
      return NextResponse.json(
        {
          success: false,
          error: 'Session required. Provide X-Session-Id header or Authorization: Bearer <sessionId>.',
          code: 'SESSION_REQUIRED',
        },
        { status: 401 }
      );
    }

    // 2. Validate session (includes auto-refresh within renewal threshold)
    const session = manager.validateSession(sessionId);

    if (!session) {
      return NextResponse.json(
        {
          success: false,
          error: 'Invalid or expired session.',
          code: 'SESSION_INVALID',
        },
        { status: 401 }
      );
    }

    // 3. Inject session info into request
    (req as Request & { session?: Session; userId?: string }).session = session;
    (req as Request & { session?: Session; userId?: string }).userId = session.userId;

    // 4. Call the wrapped handler
    return handler(req, ctx);
  };
}
