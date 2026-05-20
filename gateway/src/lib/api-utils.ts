// ─── Utilidades compartidas para API Routes ──────────────────────────
// Patrones reutilizables: paginación cursor, SQL aggregation helper.
// INVARIANT 3 — 500MB RAM: todos los límites protegen contra fuga de memoria.

import { NextRequest } from "next/server";

/** Resultado de parsear parámetros de paginación */
export interface PaginationParams {
  limit: number;     // Máximo de registros a retornar
  cursor?: string;   // ID del último registro de la página anterior
}

/** Valores por defecto seguros para INVARIANT 3 (500MB RAM) */
const DEFAULT_LIMIT = 50;
const MAX_LIMIT = 200;

/**
 * Extrae parámetros de paginación de un NextRequest.
 * Soporta: ?limit=50&cursor=abc123
 *
 * - limit: default 50, max 200 (protege RAM)
 * - cursor: ID del último registro visto (paginación keyset)
 *
 * Keyset pagination (id > cursor) es más eficiente que OFFSET en SQLite:
 * no necesita escanear y descartar filas. Con CUIDs (ordenados por
 * timestamp de creación), el orden natural es cronológico.
 */
export function parsePagination(request: NextRequest): PaginationParams {
  const { searchParams } = new URL(request.url);

  const rawLimit = parseInt(searchParams.get("limit") ?? "", 10);
  const limit =
    Number.isFinite(rawLimit) && rawLimit > 0
      ? Math.min(rawLimit, MAX_LIMIT)
      : DEFAULT_LIMIT;

  const cursor = searchParams.get("cursor") || undefined;

  return { limit, cursor };
}

/**
 * Construye la cláusula `where` para paginación cursor (keyset pagination).
 * Usa `id > cursor` que funciona con CUID (ordenado por timestamp de creación).
 *
 * Uso:
 *   const where = { status: "active", ...cursorWhere(cursor) };
 *   const items = await db.model.findMany({ where, take: limit + 1 });
 */
export function cursorWhere(
  cursor?: string
): Record<string, unknown> {
  if (!cursor) return {};
  return { id: { gt: cursor } };
}
