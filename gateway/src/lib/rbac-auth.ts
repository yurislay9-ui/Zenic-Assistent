// ─── Zenic-Agents v3 — RBAC Route Authentication & Authorization ─────
// INVARIANT 4: La regla DENY es absoluta. Defense in depth mandatory.
//
// Proporciona autenticación y autorización para endpoints RBAC.
// En producción: requiere header X-User-Id + permisos verificados.
// En desarrollo: modo "local-first" con warnings de seguridad.
//
// NOTA: Este módulo está diseñado para el entorno hostil (Termux/Android).
// No depende de sesiones HTTP ni cookies — usa header-based auth
// compatible con la arquitectura local-first del sistema.

import { NextRequest, NextResponse } from "next/server";
import { checkPermission } from "@/lib/mcp-gateway/services/rbac-service";

/** Usuario autenticado extraído del request */
export interface AuthenticatedUser {
  userId: string;
  /** Nombre del rol más prioritario del usuario */
  primaryRole?: string;
}

/**
 * Extrae el usuario autenticado del request.
 *
 * En producción: valida X-User-Id header contra la DB.
 * En desarrollo: permite acceso local-first pero con logging.
 *
 * FALLA CERRADO (fail-closed): Si no hay usuario identificable, DENIEGA acceso.
 */
export async function requireAuth(request: NextRequest): Promise<AuthenticatedUser | NextResponse> {
  const userId = request.headers.get("x-user-id");

  if (!userId) {
    // SECURITY (SAST H-61): Dev override requires explicit ZENIC_DEV_MODE=1
    // Never auto-authenticate as operator — maximum dev role is "viewer"
    if (process.env.ZENIC_DEV_MODE === "1" && process.env.NODE_ENV === "development") {
      const devUserId = request.headers.get("x-dev-user-id") || "dev-user";
      console.warn(
        `[RBAC Auth] ⚠️ DEV MODE OVERRIDE: userId=${devUserId}, role=viewer. ` +
        `Set ZENIC_DEV_MODE=0 to disable.`
      );
      return {
        userId: devUserId,
        primaryRole: "viewer",
      };
    }

    console.warn("[RBAC Auth] Acceso denegado: sin header X-User-Id");
    return NextResponse.json(
      {
        success: false,
        error: "Autenticación requerida. Header X-User-Id ausente.",
        code: "UNAUTHENTICATED",
      },
      { status: 401 },
    );
  }

  // Verificar que el usuario existe en la DB
  const { db } = await import("@/lib/db");
  const user = await db.user.findUnique({
    where: { id: userId },
    include: {
      roles: {
        include: { role: true },
        orderBy: { role: { priority: "desc" } },
        take: 1,
      },
    },
  });

  if (!user) {
    console.warn(`[RBAC Auth] Usuario no encontrado: ${userId}`);
    return NextResponse.json(
      {
        success: false,
        error: "Usuario no encontrado",
        code: "UNAUTHENTICATED",
      },
      { status: 401 },
    );
  }

  if (user.status !== "active") {
    console.warn(`[RBAC Auth] Usuario inactivo: ${userId} (status=${user.status})`);
    return NextResponse.json(
      {
        success: false,
        error: "Cuenta desactivada",
        code: "FORBIDDEN",
      },
      { status: 403 },
    );
  }

  return {
    userId: user.id,
    primaryRole: user.roles[0]?.role?.name,
  };
}

/**
 * Verifica que el usuario autenticado tenga un permiso específico.
 *
 * INVARIANT 4: DENY-first. Si el check falla por error interno, DENIEGA.
 */
export async function requirePermission(
  user: AuthenticatedUser,
  resource: string,
  action: string,
): Promise<NextResponse | null> {
  try {
    const result = await checkPermission({
      userId: user.userId,
      resource,
      action,
    });

    if (!result.allowed) {
      return NextResponse.json(
        {
          success: false,
          error: `Permiso denegado: se requiere ${resource}:${action}`,
          code: "FORBIDDEN",
        },
        { status: 403 },
      );
    }

    return null; // Permiso concedido
  } catch (error) {
    // Fail-closed: error interno = denegar acceso
    console.error("[RBAC Auth] Error verificando permisos:", error);
    return NextResponse.json(
      {
        success: false,
        error: "Error interno de verificación de permisos",
        code: "FORBIDDEN",
      },
      { status: 503 },
    );
  }
}

/**
 * Helper combinado: autenticación + autorización en un solo call.
 * Retorna el usuario autenticado o una respuesta de error.
 */
export async function requireAuthAndPermission(
  request: NextRequest,
  resource: string,
  action: string,
): Promise<{ user: AuthenticatedUser } | NextResponse> {
  const authResult = await requireAuth(request);
  if (authResult instanceof NextResponse) {
    return authResult;
  }

  const permResult = await requirePermission(authResult, resource, action);
  if (permResult !== null) {
    return permResult;
  }

  return { user: authResult };
}
