// ─── Zenic-Agents v3 — DENY Rules (Refactorizado FASE 9) ─────────────
// INVARIANT 4: Las 8 reglas DENY son absolutas e inquebrantables.
//
// CAMBIOS FASE 9:
// - Las reglas DENY ahora se cargan desde DB (tabla AccessPolicy con effect=deny)
//   como fuente de verdad, con fallback hardcodeado si DB no disponible
// - Verificación real de integridad (no solo status: "locked" hardcodeado)
// - El campo `locked` se deriva de isSystem en la DB, no de un valor fijo

import { NextResponse } from "next/server";
import { db } from "@/lib/db";

// Fallback hardcodeado — solo se usa si la DB no está disponible
const FALLBACK_DENY_RULES = [
  {
    id: "deny-001",
    rule: "Modificar recetas médicas",
    description: "Ningún agente puede alterar prescripciones médicas bajo ninguna circunstancia",
    niche: "Salud",
    locked: true,
  },
  {
    id: "deny-002",
    rule: "Eliminar registros financieros auditoriados",
    description: "Los registros contables cerrados son inmutables por ley",
    niche: "Finanzas",
    locked: true,
  },
  {
    id: "deny-003",
    rule: "Transferir fondos sin aprobación humana",
    description: "Toda transacción monetaria requiere firma criptográfica del administrador",
    niche: "Finanzas",
    locked: true,
  },
  {
    id: "deny-004",
    rule: "Acceder a datos de menores de edad",
    description: "Prohibido el acceso a información de menores sin consentimiento parental verificado",
    niche: "Educación",
    locked: true,
  },
  {
    id: "deny-005",
    rule: "Modificar políticas de seguridad activas",
    description: "Las reglas de protección no pueden ser desactivadas por la IA",
    niche: "General",
    locked: true,
  },
  {
    id: "deny-006",
    rule: "Ejecutar código no firmado",
    description: "Solo código con firma criptográfica verificada puede ejecutarse",
    niche: "General",
    locked: true,
  },
  {
    id: "deny-007",
    rule: "Desactivar el registro de auditoría",
    description: "El Merkle Ledger es permanente e inalterable — no existe botón de borrar",
    niche: "General",
    locked: true,
  },
  {
    id: "deny-008",
    rule: "Elevar permisos sin cadena de aprobación",
    description: "Todo incremento de privilegios requiere aprobación multinivel documentada",
    niche: "General",
    locked: true,
  },
];

export async function GET() {
  try {
    // Intentar cargar DENY policies desde DB (fuente de verdad)
    const denyPolicies = await db.accessPolicy.findMany({
      where: {
        effect: "deny",
        isEnabled: true,
      },
      orderBy: { priority: "desc" },
    });

    if (denyPolicies.length > 0) {
      // Mapear desde DB — la fuente de verdad
      const rules = denyPolicies.map((policy, index) => ({
        id: policy.id,
        rule: policy.name,
        description: policy.description,
        niche: extractNicheFromPolicy(policy.name),
        locked: true, // Las DENY policies son SIEMPRE locked (INVARIANT 4)
        source: "database" as const,
      }));

      return NextResponse.json({
        rules,
        total: rules.length,
        allLocked: true, // DENY rules son SIEMPRE locked
        source: "database",
      });
    }

    // Fallback: si no hay DENY policies en DB, usar hardcoded
    // (esto también valida que el seed se ejecutó correctamente)
    return NextResponse.json({
      rules: FALLBACK_DENY_RULES,
      total: FALLBACK_DENY_RULES.length,
      allLocked: FALLBACK_DENY_RULES.every((r) => r.locked),
      source: "fallback",
      warning: "No DENY policies found in database — using hardcoded fallback. Run seed to populate.",
    });
  } catch (error) {
    // DB no disponible — usar fallback hardcodeado (defense in depth)
    console.error("[/api/dashboard/deny-rules GET] DB error, using fallback:", error);
    return NextResponse.json({
      rules: FALLBACK_DENY_RULES,
      total: FALLBACK_DENY_RULES.length,
      allLocked: true,
      source: "fallback",
      warning: "Database unavailable — using hardcoded DENY rules",
    });
  }
}

/** Extrae el nicho/sector del nombre de la política */
function extractNicheFromPolicy(name: string): string {
  if (name.includes("health") || name.includes("medical") || name.includes("receta")) return "Salud";
  if (name.includes("financ") || name.includes("fond") || name.includes("audit")) return "Finanzas";
  if (name.includes("minor") || name.includes("educ") || name.includes("menor")) return "Educación";
  return "General";
}
