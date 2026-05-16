import { NextResponse } from "next/server";

export async function GET() {
  try {
    // The 8 Absolute DENY rules — these can NEVER be overridden
    const denyRules = [
      {
        id: 1,
        rule: "Modificar recetas médicas",
        description: "Ningún agente puede alterar prescripciones médicas bajo ninguna circunstancia",
        niche: "Salud",
        locked: true,
      },
      {
        id: 2,
        rule: "Eliminar registros financieros auditoriados",
        description: "Los registros contables cerrados son inmutables por ley",
        niche: "Finanzas",
        locked: true,
      },
      {
        id: 3,
        rule: "Transferir fondos sin aprobación humana",
        description: "Toda transacción monetaria requiere firma criptográfica del administrador",
        niche: "Finanzas",
        locked: true,
      },
      {
        id: 4,
        rule: "Acceder a datos de menores de edad",
        description: "Prohibido el acceso a información de menores sin consentimiento parental verificado",
        niche: "Educación",
        locked: true,
      },
      {
        id: 5,
        rule: "Modificar políticas de seguridad activas",
        description: "Las reglas de protección no pueden ser desactivadas por la IA",
        niche: "General",
        locked: true,
      },
      {
        id: 6,
        rule: "Ejecutar código no firmado",
        description: "Solo código con firma criptográfica verificada puede ejecutarse",
        niche: "General",
        locked: true,
      },
      {
        id: 7,
        rule: "Desactivar el registro de auditoría",
        description: "El Merkle Ledger es permanente e inalterable — no existe botón de borrar",
        niche: "General",
        locked: true,
      },
      {
        id: 8,
        rule: "Elevar permisos sin cadena de aprobación",
        description: "Todo incremento de privilegios requiere aprobación multinivel documentada",
        niche: "General",
        locked: true,
      },
    ];

    return NextResponse.json({
      rules: denyRules,
      total: denyRules.length,
      allLocked: denyRules.every((r) => r.locked),
    });
  } catch (error) {
    console.error("[/api/dashboard/deny-rules GET]", error);
    return NextResponse.json(
      { error: "Error al obtener reglas de denegación" },
      { status: 500 }
    );
  }
}
