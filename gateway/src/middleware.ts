// Zenic-Agents v3.0 — Middleware de Protección de Rutas (Refactorizado FASE 9)
//
// INVARIANT 4: La regla DENY es absoluta.
// Este middleware protege rutas de API sensibles y requiere
// autenticación header-based (X-User-Id) para operaciones críticas.
//
// CAMBIOS FASE 9:
// - En desarrollo: ya NO permite acceso sin auth a rutas sensibles.
//   Se usa "local-seller" como usuario por defecto para operaciones
//   de solo lectura, pero rutas administrativas requieren X-User-Id explícito.
// - Rutas protegidas expandidas: RBAC, policies, audit, users, seed.
// - Rutas de solo lectura permitidas en desarrollo sin header.

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Rutas que NUNCA deben ser accesibles sin autenticación
// ni siquiera en desarrollo
const RUTAS_BLOQUEADAS_SIEMPRE = [
  "/api/seed",                     // Población de BD — extremadamente peligroso
  "/api/v1/subscription/saga/",    // Saga lifecycle — operaciones financieras
  "/api/v1/subscription/payment/", // Pagos — operaciones financieras
];

// Rutas administrativas que requieren header X-User-Id
// incluso en desarrollo
const RUTAS_ADMIN_REQUIEREN_AUTH = [
  "/api/rbac/assign",              // Asignar roles
  "/api/rbac/revoke",              // Revocar roles
  "/api/rbac/roles",               // CRUD de roles (POST/PUT/DELETE)
  "/api/policies",                 // CRUD de políticas (POST/PUT/DELETE)
  "/api/v1/policies",              // Declarative policies
  "/api/v1/policy-engine",         // Policy engine admin
  "/api/v1/hitl/",                 // HITL operations
  "/api/v1/subscription/",         // Subscription management
  "/api/users",                    // User management
];

// Rutas de solo lectura permitidas con usuario local en desarrollo
const RUTAS_LECTURA_PERMITIDAS_DEV = [
  "/api/rbac/check",               // Check permission (read-only)
  "/api/rbac/permissions",         // List permissions (read-only)
  "/api/audit",                    // Read audit logs
  "/api/dashboard/",               // Dashboard data
  "/api/mcp/servers",              // MCP server list
  "/api/mcp/tools",                // MCP tool list
];

// Rutas estáticas que no requieren protección
const RUTAS_PUBLICAS = [
  "/_next/",
  "/favicon.ico",
  "/logo.svg",
  "/robots.txt",
  "/api/route",                    // Health check
];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const method = request.method;

  // Permitir archivos estáticos
  if (RUTAS_PUBLICAS.some((ruta) => pathname.startsWith(ruta))) {
    return NextResponse.next();
  }

  // ─── Rutas BLOQUEADAS SIEMPRE (ni siquiera en desarrollo) ───────
  for (const ruta of RUTAS_BLOQUEADAS_SIEMPRE) {
    if (pathname.startsWith(ruta)) {
      // En desarrollo, /api/seed solo vía prisma db seed
      if (pathname === "/api/seed" && process.env.NODE_ENV === "development") {
        return NextResponse.json(
          { error: "Ruta bloqueada. Ejecutar prisma db seed directamente." },
          { status: 403 },
        );
      }
      return NextResponse.json(
        { error: "Acceso denegado. Se requiere autenticación.", code: "UNAUTHENTICATED" },
        { status: 401 },
      );
    }
  }

  // ─── Producción: todas las rutas de API requieren X-User-Id ──────
  if (process.env.NODE_ENV === "production") {
    if (pathname.startsWith("/api/")) {
      const userId = request.headers.get("x-user-id");
      if (!userId) {
        return NextResponse.json(
          { error: "Acceso denegado. Se requiere autenticación.", code: "UNAUTHENTICATED" },
          { status: 401 },
        );
      }
    }
    return NextResponse.next();
  }

  // ─── Desarrollo: modo local-first con protecciones mínimas ───────
  // Las rutas administrativas requieren header X-User-Id explícito
  for (const ruta of RUTAS_ADMIN_REQUIEREN_AUTH) {
    if (pathname.startsWith(ruta) && method !== "GET") {
      const userId = request.headers.get("x-user-id");
      if (!userId) {
        return NextResponse.json(
          {
            error: "Operación administrativa requiere header X-User-Id",
            code: "UNAUTHENTICATED",
            hint: "Incluye header: X-User-Id: <tu-user-id>",
          },
          { status: 401 },
        );
      }
    }
  }

  // Para rutas de lectura en desarrollo, inyectar usuario local si no hay header
  if (RUTAS_LECTURA_PERMITIDAS_DEV.some((ruta) => pathname.startsWith(ruta))) {
    const userId = request.headers.get("x-user-id");
    if (!userId) {
      // Inyectar header X-User-Id para que los endpoints usen "local-seller"
      const requestHeaders = new Headers(request.headers);
      requestHeaders.set("x-user-id", "local-seller");
      return NextResponse.next({
        request: {
          headers: requestHeaders,
        },
      });
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Aplicar a todas las rutas excepto:
     * - _next/static (archivos estáticos)
     * - _next/image (optimizador de imágenes)
     * - favicon.ico
     */
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
