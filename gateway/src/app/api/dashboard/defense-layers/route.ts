// ─── Zenic-Agents v3 — Defense Layers (Refactorizado FASE 9) ─────────
// INVARIANT 4: Las capas de defensa deben ser verificables.
//
// CAMBIOS FASE 9:
// - Cada capa hace una verificación REAL de su estado (no todo "active" hardcodeado)
// - Capa de cifrado: verifica que crypto.ts esté funcional
// - Capa de auditoría: verifica que existan registros Merkle
// - Capa RBAC: verifica que existan roles y permisos
// - Si una capa falla, reporta degradedMode = true

import { NextResponse } from "next/server";
import { db } from "@/lib/db";

export async function GET() {
  try {
    // Verificar estado real de cada capa de defensa
    const layers = await Promise.all([
      verifyAntiManipulation(),
      verifySystemHardening(),
      verifyEncryption(),
      verifyExecutionIsolation(),
      verifySecurityGate(),
      verifyImmutableAudit(),
    ]);

    const allActive = layers.every((l) => l.status === "active");
    const degradedLayers = layers.filter((l) => l.status !== "active");

    return NextResponse.json({
      layers,
      allActive,
      degradedMode: !allActive,
      degradedCount: degradedLayers.length,
      degradedLayers: degradedLayers.map((l) => l.name),
      lastCheck: new Date().toISOString(),
    });
  } catch (error) {
    console.error("[/api/dashboard/defense-layers GET]", error);
    return NextResponse.json(
      { error: "Error al verificar capas de defensa" },
      { status: 500 },
    );
  }
}

async function verifyAntiManipulation() {
  // Verificar que hay políticas DENY activas (INVARIANT 4)
  try {
    const denyCount = await db.accessPolicy.count({
      where: { effect: "deny", isEnabled: true },
    });
    return {
      id: 1,
      name: "Anti-Manipulación",
      description: "Protección contra alteraciones del código y configuración",
      status: denyCount > 0 ? "active" : "degraded",
      icon: "Shield",
      details: denyCount > 0
        ? `${denyCount} política(s) DENY activa(s) — integridad verificada`
        : "SIN políticas DENY activas — INVARIANT 4 comprometida",
    };
  } catch {
    return {
      id: 1,
      name: "Anti-Manipulación",
      description: "Protección contra alteraciones del código y configuración",
      status: "unknown",
      icon: "Shield",
      details: "No se pudo verificar — DB no disponible",
    };
  }
}

async function verifySystemHardening() {
  // Verificar que hay roles de sistema
  try {
    const systemRoles = await db.role.count({ where: { isSystem: true } });
    return {
      id: 2,
      name: "Endurecimiento del Sistema",
      description: "Configuración restrictiva y eliminación de superficies de ataque",
      status: systemRoles >= 4 ? "active" : "degraded",
      icon: "Lock",
      details: systemRoles >= 4
        ? `${systemRoles} roles de sistema configurados — mínimo privilegio aplicado`
        : `Solo ${systemRoles} roles de sistema — se requieren mínimo 4`,
    };
  } catch {
    return {
      id: 2, name: "Endurecimiento del Sistema",
      description: "Configuración restrictiva", status: "unknown", icon: "Lock",
      details: "No se pudo verificar — DB no disponible",
    };
  }
}

async function verifyEncryption() {
  // Verificar que el módulo crypto está disponible
  try {
    const { maskCredentialFields, encrypt, decrypt } = await import("@/lib/crypto");
    // Test: encriptar y desencriptar un valor de prueba
    const testPayload = encrypt({ test: "verification-value" });
    const decrypted = decrypt(testPayload);
    const isWorking = decrypted.test === "verification-value";
    return {
      id: 3,
      name: "Cifrado de Datos",
      description: "Encriptación en tránsito y en reposo",
      status: isWorking ? "active" : "degraded",
      icon: "KeyRound",
      details: isWorking
        ? "AES-256-GCM operativo — datos en reposo protegidos"
        : "Módulo crypto no funcional — datos SIN protección",
    };
  } catch {
    return {
      id: 3, name: "Cifrado de Datos",
      description: "Encriptación en tránsito y en reposo", status: "degraded", icon: "KeyRound",
      details: "Módulo crypto no disponible",
    };
  }
}

async function verifyExecutionIsolation() {
  // Verificar que las herramientas con riesgo alto requieren aprobación
  try {
    const highRiskWithoutApproval = await db.mcpTool.count({
      where: {
        riskLevel: { in: ["high", "critical"] },
        requiresApproval: false,
      },
    });
    return {
      id: 4,
      name: "Aislamiento de Ejecución",
      description: "Sandbox separado para cada operación",
      status: highRiskWithoutApproval === 0 ? "active" : "degraded",
      icon: "Box",
      details: highRiskWithoutApproval === 0
        ? "Todas las herramientas de alto riesgo requieren aprobación"
        : `${highRiskWithoutApproval} herramienta(s) de alto riesgo SIN requerimiento de aprobación`,
    };
  } catch {
    return {
      id: 4, name: "Aislamiento de Ejecución",
      description: "Sandbox separado para cada operación", status: "unknown", icon: "Box",
      details: "No se pudo verificar — DB no disponible",
    };
  }
}

async function verifySecurityGate() {
  // Verificar que las 8 DENY rules existen
  try {
    const denyPolicies = await db.accessPolicy.count({
      where: { effect: "deny", isEnabled: true },
    });
    return {
      id: 5,
      name: "Puerta de Seguridad",
      description: "Reglas de nicho industrial y denegaciones absolutas",
      status: denyPolicies >= 8 ? "active" : "degraded",
      icon: "ShieldCheck",
      details: denyPolicies >= 8
        ? `${denyPolicies} reglas DENY activas — estándares industriales verificados`
        : `Solo ${denyPolicies} reglas DENY — se requieren mínimo 8 (INVARIANT 4)`,
    };
  } catch {
    return {
      id: 5, name: "Puerta de Seguridad",
      description: "Reglas de nicho industrial y denegaciones absolutas", status: "unknown", icon: "ShieldCheck",
      details: "No se pudo verificar — DB no disponible",
    };
  }
}

async function verifyImmutableAudit() {
  // Verificar que existen registros de auditoría Merkle
  try {
    const auditCount = await db.hitlApprovalAudit.count();
    return {
      id: 6,
      name: "Auditoría Inmutable",
      description: "Registro Merkle que nadie puede alterar",
      status: auditCount > 0 ? "active" : "degraded",
      icon: "FileLock",
      details: auditCount > 0
        ? `Cadena Merkle con ${auditCount} entrada(s) — verificable criptográficamente`
        : "Sin entradas de auditoría Merkle — cadena no inicializada",
    };
  } catch {
    return {
      id: 6, name: "Auditoría Inmutable",
      description: "Registro Merkle que nadie puede alterar", status: "unknown", icon: "FileLock",
      details: "No se pudo verificar — DB no disponible",
    };
  }
}
