// Zenic-Agents v3.0 — Middleware de Protección de Rutas (FASE 3: Integración)
//
// INVARIANT 4: La regla DENY es absoluta.
// Este middleware protege rutas de API sensibles y requiere
// autenticación header-based (X-User-Id) para operaciones críticas.
//
// FASE 3 - Cambios aplicados:
// - CORS restrictivo con allowlist (F1/E1)
// - Rate limiting con 6 tiers (F2/E2)
// - Query param sanitización (F1/#20)
// - Security headers: CSP, HSTS, X-Frame-Options, etc. (G1/G2)
// - HTTPS enforcement en producción (G1)
// - Audit logging para operaciones críticas (F3/#32)

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// ─── Configuración CORS Restrictiva (#24) ─────────────────────────────

const ALLOWED_ORIGINS = (() => {
  const envOrigins = process.env.ZENIC_CORS_ORIGINS;
  if (envOrigins && envOrigins !== "*") {
    return envOrigins.split(",").map((o) => o.trim()).filter(Boolean);
  }
  // Defaults seguros — solo localhost en desarrollo
  if (process.env.NODE_ENV === "development") {
    return [
      "http://localhost:3000",
      "http://127.0.0.1:3000",
    ];
  }
  // Producción: DEBE configurarse via ZENIC_CORS_ORIGINS
  return [];
})();

const CORS_ALLOWED_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"];
const CORS_MAX_AGE = 86400; // 24 horas

function handleCors(request: NextRequest): NextResponse | null {
  const origin = request.headers.get("origin");
  const isPreflight = request.method === "OPTIONS";

  // Sin origin = no es CORS request, permitir
  if (!origin) return null;

  // Verificar origin contra allowlist
  const isAllowedOrigin = ALLOWED_ORIGINS.includes(origin) ||
    (process.env.NODE_ENV === "development" && origin.includes("localhost"));

  if (!isAllowedOrigin) {
    if (isPreflight) {
      return new NextResponse(null, { status: 403 });
    }
    // Para requests normales, permitir pero sin CORS headers (browser bloquea)
    return null;
  }

  if (isPreflight) {
    const response = new NextResponse(null, { status: 204 });
    response.headers.set("Access-Control-Allow-Origin", origin);
    response.headers.set("Access-Control-Allow-Methods", CORS_ALLOWED_METHODS.join(", "));
    response.headers.set("Access-Control-Allow-Headers", "Content-Type, X-User-Id, X-Session-Id, Authorization, X-API-Key");
    response.headers.set("Access-Control-Max-Age", String(CORS_MAX_AGE));
    response.headers.set("Access-Control-Allow-Credentials", "true");
    return response;
  }

  return null; // Continuar — CORS headers se añaden en applySecurityHeaders
}

// ─── Rate Limiting (#26) ─────────────────────────────────────────────

interface RateLimitEntry {
  count: number;
  resetAt: number;
}

const rateLimitStore = new Map<string, RateLimitEntry>();

const RATE_LIMIT_TIERS: Record<string, { windowMs: number; max: number }> = {
  "/api/v1/subscription/payment": { windowMs: 60_000, max: 5 },      // 5/min pagos
  "/api/v1/hitl/": { windowMs: 60_000, max: 30 },                    // 30/min HITL
  "/api/v1/subscription/": { windowMs: 60_000, max: 20 },             // 20/min suscripciones
  "/api/rbac/": { windowMs: 60_000, max: 60 },                        // 60/min RBAC
  "/api/v1/policies": { windowMs: 60_000, max: 30 },                  // 30/min políticas
  "/api/v1/policy-engine/": { windowMs: 60_000, max: 30 },            // 30/min policy engine
  default: { windowMs: 60_000, max: 100 },                             // 100/min default
};

function checkRateLimit(request: NextRequest): NextResponse | null {
  const { pathname } = request.nextUrl;
  const clientId = request.headers.get("x-user-id") ||
    request.headers.get("x-forwarded-for") ||
    request.headers.get("x-real-ip") ||
    "anonymous";

  // Encontrar tier aplicable
  let tier = RATE_LIMIT_TIERS.default;
  for (const [prefix, config] of Object.entries(RATE_LIMIT_TIERS)) {
    if (prefix !== "default" && pathname.startsWith(prefix)) {
      tier = config;
      break;
    }
  }

  const key = `${clientId}:${pathname.substring(0, 50)}`;
  const now = Date.now();

  // Limpiar entradas expiradas periódicamente
  if (rateLimitStore.size > 10000) {
    for (const [k, v] of rateLimitStore) {
      if (v.resetAt < now) rateLimitStore.delete(k);
    }
  }

  const entry = rateLimitStore.get(key);
  if (!entry || entry.resetAt < now) {
    rateLimitStore.set(key, { count: 1, resetAt: now + tier.windowMs });
    return null;
  }

  entry.count++;
  if (entry.count > tier.max) {
    const retryAfter = Math.ceil((entry.resetAt - now) / 1000);
    return NextResponse.json(
      {
        error: "Demasiadas solicitudes. Intenta de nuevo más tarde.",
        code: "RATE_LIMITED",
        retryAfter,
      },
      {
        status: 429,
        headers: {
          "Retry-After": String(retryAfter),
          "X-RateLimit-Limit": String(tier.max),
          "X-RateLimit-Remaining": "0",
          "X-RateLimit-Reset": String(Math.ceil(entry.resetAt / 1000)),
        },
      },
    );
  }

  return null; // Dentro del límite
}

// ─── Query Param Sanitización (#20) ──────────────────────────────────

const SQL_INJECTION_PATTERNS = [
  /(\b(union\s+select|select\s+.+\s+from|insert\s+into|delete\s+from|drop\s+table|alter\s+table|exec\s*\(|execute\s*\()\b)/i,
  /(--|;|\/\*|\*\/|xp_|0x[0-9a-f]{2})/i,
  /('.*\b(or|and)\b.*')/i,
];

const XSS_PATTERNS = [
  /<script[\s>]/i,
  /javascript\s*:/i,
  /on\w+\s*=/i,
  /<iframe[\s>]/i,
  /<embed[\s>]/i,
  /<object[\s>]/i,
];

function sanitizeQueryParams(request: NextRequest): NextResponse | null {
  const { searchParams } = request.nextUrl;

  for (const [key, value] of searchParams.entries()) {
    // Verificar SQL injection
    for (const pattern of SQL_INJECTION_PATTERNS) {
      if (pattern.test(value)) {
        console.warn(`[sanitize] SQL injection attempt detected in query param "${key}": ${value.substring(0, 100)}`);
        return NextResponse.json(
          { error: "Parámetro de consulta inválido.", code: "INVALID_INPUT" },
          { status: 400 },
        );
      }
    }

    // Verificar XSS
    for (const pattern of XSS_PATTERNS) {
      if (pattern.test(value)) {
        console.warn(`[sanitize] XSS attempt detected in query param "${key}": ${value.substring(0, 100)}`);
        return NextResponse.json(
          { error: "Parámetro de consulta inválido.", code: "INVALID_INPUT" },
          { status: 400 },
        );
      }
    }

    // Longitud máxima
    if (value.length > 500) {
      return NextResponse.json(
        { error: "Parámetro de consulta demasiado largo.", code: "INVALID_INPUT" },
        { status: 400 },
      );
    }
  }

  return null;
}

// ─── Security Headers (G1/G2) ───────────────────────────────────────

function applySecurityHeaders(response: NextResponse, request: NextRequest): NextResponse {
  const isProd = process.env.NODE_ENV === "production";

  // Content-Security-Policy
  response.headers.set(
    "Content-Security-Policy",
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; " +
    "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; " +
    "base-uri 'self'; form-action 'self'",
  );

  // X-Frame-Options
  response.headers.set("X-Frame-Options", "DENY");

  // X-Content-Type-Options
  response.headers.set("X-Content-Type-Options", "nosniff");

  // X-XSS-Protection (disabled — CSP is preferred)
  response.headers.set("X-XSS-Protection", "0");

  // Referrer-Policy
  response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");

  // Permissions-Policy
  response.headers.set(
    "Permissions-Policy",
    "camera=(), microphone=(), geolocation=(), payment=(), usb=(), " +
    "magnetometer=(), gyroscope=(), accelerometer=()",
  );

  // HSTS (solo en producción)
  if (isProd) {
    response.headers.set(
      "Strict-Transport-Security",
      "max-age=63072000; includeSubDomains; preload",
    );
  }

  // Cache-Control para rutas de API
  if (request.nextUrl.pathname.startsWith("/api/")) {
    response.headers.set("Cache-Control", "no-store, no-cache, must-revalidate, private");
  }

  // CORS header para responses normales
  const origin = request.headers.get("origin");
  if (origin && (
    ALLOWED_ORIGINS.includes(origin) ||
    (process.env.NODE_ENV === "development" && origin.includes("localhost"))
  )) {
    response.headers.set("Access-Control-Allow-Origin", origin);
    response.headers.set("Access-Control-Allow-Credentials", "true");
  }

  return response;
}

// ─── HTTPS Enforcement (G1) ──────────────────────────────────────────

function enforceHttps(request: NextRequest): NextResponse | null {
  if (process.env.NODE_ENV !== "production") return null;

  const proto = request.headers.get("x-forwarded-proto");
  if (proto && proto !== "https") {
    const httpsUrl = request.nextUrl.clone();
    httpsUrl.protocol = "https:";
    return NextResponse.redirect(httpsUrl, 301);
  }

  return null;
}

// ─── Rutas protegidas ────────────────────────────────────────────────

const RUTAS_BLOQUEADAS_SIEMPRE = [
  "/api/seed",                     // Población de BD — extremadamente peligroso
  "/api/v1/subscription/saga/",    // Saga lifecycle — operaciones financieras
  "/api/v1/subscription/payment/", // Pagos — operaciones financieras
];

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

const RUTAS_LECTURA_PERMITIDAS_DEV = [
  "/api/rbac/check",               // Check permission (read-only)
  "/api/rbac/permissions",         // List permissions (read-only)
  "/api/audit",                    // Read audit logs
  "/api/dashboard/",               // Dashboard data
  "/api/mcp/servers",              // MCP server list
  "/api/mcp/tools",                // MCP tool list
];

const RUTAS_PUBLICAS = [
  "/_next/",
  "/favicon.ico",
  "/logo.svg",
  "/robots.txt",
  "/api/route",                    // Health check
];

// ─── Middleware Principal ────────────────────────────────────────────

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const method = request.method;

  // 1. HTTPS enforcement (producción)
  const httpsRedirect = enforceHttps(request);
  if (httpsRedirect) return httpsRedirect;

  // 2. Permitir archivos estáticos
  if (RUTAS_PUBLICAS.some((ruta) => pathname.startsWith(ruta))) {
    return applySecurityHeaders(NextResponse.next(), request);
  }

  // 3. CORS preflight
  const corsResponse = handleCors(request);
  if (corsResponse) return applySecurityHeaders(corsResponse, request);

  // 4. Query param sanitización
  const sanitizationError = sanitizeQueryParams(request);
  if (sanitizationError) return applySecurityHeaders(sanitizationError, request);

  // 5. Rate limiting
  const rateLimitResponse = checkRateLimit(request);
  if (rateLimitResponse) return applySecurityHeaders(rateLimitResponse, request);

  // 6. Rutas BLOQUEADAS SIEMPRE
  for (const ruta of RUTAS_BLOQUEADAS_SIEMPRE) {
    if (pathname.startsWith(ruta)) {
      if (pathname === "/api/seed" && process.env.NODE_ENV === "development") {
        return applySecurityHeaders(
          NextResponse.json(
            { error: "Ruta bloqueada. Ejecutar prisma db seed directamente." },
            { status: 403 },
          ),
          request,
        );
      }
      return applySecurityHeaders(
        NextResponse.json(
          { error: "Acceso denegado. Se requiere autenticación.", code: "UNAUTHENTICATED" },
          { status: 401 },
        ),
        request,
      );
    }
  }

  // 7. Producción: todas las rutas de API requieren X-User-Id
  if (process.env.NODE_ENV === "production") {
    if (pathname.startsWith("/api/")) {
      const userId = request.headers.get("x-user-id");
      if (!userId) {
        return applySecurityHeaders(
          NextResponse.json(
            { error: "Acceso denegado. Se requiere autenticación.", code: "UNAUTHENTICATED" },
            { status: 401 },
          ),
          request,
        );
      }
    }
    return applySecurityHeaders(NextResponse.next(), request);
  }

  // 8. Desarrollo: modo local-first con protecciones mínimas
  for (const ruta of RUTAS_ADMIN_REQUIEREN_AUTH) {
    if (pathname.startsWith(ruta) && method !== "GET") {
      const userId = request.headers.get("x-user-id");
      if (!userId) {
        return applySecurityHeaders(
          NextResponse.json(
            {
              error: "Operación administrativa requiere header X-User-Id",
              code: "UNAUTHENTICATED",
              hint: "Incluye header: X-User-Id: <tu-user-id>",
            },
            { status: 401 },
          ),
          request,
        );
      }
    }
  }

  // 9. Rutas de lectura en desarrollo: inyectar usuario local si no hay header
  if (RUTAS_LECTURA_PERMITIDAS_DEV.some((ruta) => pathname.startsWith(ruta))) {
    const userId = request.headers.get("x-user-id");
    if (!userId) {
      const requestHeaders = new Headers(request.headers);
      requestHeaders.set("x-user-id", "local-seller");
      return applySecurityHeaders(
        NextResponse.next({
          request: { headers: requestHeaders },
        }),
        request,
      );
    }
  }

  return applySecurityHeaders(NextResponse.next(), request);
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
