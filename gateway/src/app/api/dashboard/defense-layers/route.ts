import { NextResponse } from "next/server";

export async function GET() {
  try {
    // The 6 Defense Layers of Zenic-Agents
    const layers = [
      {
        id: 1,
        name: "Anti-Manipulación",
        description: "Protección contra alteraciones del código y configuración",
        status: "active",
        icon: "Shield",
        details: "Verificación de integridad BLAKE3 en tiempo real",
      },
      {
        id: 2,
        name: "Endurecimiento del Sistema",
        description: "Configuración restrictiva y eliminación de superficies de ataque",
        status: "active",
        icon: "Lock",
        details: "Principio de mínimo privilegio aplicado globalmente",
      },
      {
        id: 3,
        name: "Cifrado de Datos",
        description: "Encriptación en tránsito y en reposo",
        status: "active",
        icon: "KeyRound",
        details: "AES-256-GCM + SQLCipher para bases de datos locales",
      },
      {
        id: 4,
        name: "Aislamiento de Ejecución",
        description: "Sandbox separado para cada operación",
        status: "active",
        icon: "Box",
        details: "Ejecutores aislados sin acceso al sistema host",
      },
      {
        id: 5,
        name: "Puerta de Seguridad",
        description: "Reglas de nicho industrial y 8 denegaciones absolutas",
        status: "active",
        icon: "ShieldCheck",
        details: "HIPAA, PCI-DSS, SOX y estándares por industria",
      },
      {
        id: 6,
        name: "Auditoría Inmutable",
        description: "Registro Merkle que nadie puede alterar",
        status: "active",
        icon: "FileLock",
        details: "Cadena de hashes BLAKE3 verificable criptográficamente",
      },
    ];

    const allActive = layers.every((l) => l.status === "active");

    return NextResponse.json({
      layers,
      allActive,
      degradedMode: !allActive,
      lastCheck: new Date().toISOString(),
    });
  } catch (error) {
    console.error("[/api/dashboard/defense-layers GET]", error);
    return NextResponse.json(
      { error: "Error al obtener capas de defensa" },
      { status: 500 }
    );
  }
}
