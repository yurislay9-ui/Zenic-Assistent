import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

/** Fusiona clases Tailwind sin conflictos (shadcn/ui estándar) */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Sanitiza texto de usuario contra XSS.
 * Escapa <, >, &, ", ' para prevenir inyección HTML.
 * INVARIANT 4 — defensa en profundidad, la regla DENY es absoluta.
 */
export function sanitizeInput(input: string): string {
  return input
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#x27;")
}

/**
 * Debounce genérico — evita llamadas excesivas en búsqueda/scroll.
 * Esencial para INVARIANT 3 (500MB RAM, Termux).
 */
export function debounce<T extends (...args: unknown[]) => void>(
  fn: T,
  delay: number
): (...args: Parameters<T>) => void {
  let timeoutId: ReturnType<typeof setTimeout>
  return (...args: Parameters<T>) => {
    clearTimeout(timeoutId)
    timeoutId = setTimeout(() => fn(...args), delay)
  }
}

/**
 * Formatea un timestamp ISO a fecha legible en español.
 * Sin dependencias externas (date-fns eliminado en FASE 1).
 */
export function formatDate(date: string | Date, locale = "es"): string {
  const d = typeof date === "string" ? new Date(date) : date
  if (isNaN(d.getTime())) return "—"
  return d.toLocaleDateString(`${locale}-ES`, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  })
}

/**
 * Formatea un timestamp ISO a fecha+hora legible.
 */
export function formatDateTime(date: string | Date, locale = "es"): string {
  const d = typeof date === "string" ? new Date(date) : date
  if (isNaN(d.getTime())) return "—"
  return d.toLocaleString(`${locale}-ES`, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

/**
 * Trunca texto a longitud máxima con elipsis.
 */
export function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text
  return text.slice(0, maxLength - 1) + "…"
}

/**
 * Parsea JSON de forma segura. Retorna fallback si falla.
 * Centralizado para evitar duplicación entre audit/policies/routes.
 */
export function safeJsonParse(str: string | null, fallback: unknown = null): unknown {
  if (!str) return fallback
  try {
    return JSON.parse(str)
  } catch {
    return fallback
  }
}
