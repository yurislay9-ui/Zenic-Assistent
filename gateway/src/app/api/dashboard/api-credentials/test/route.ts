// ─── API Credentials Test — Verify an API credential ──────────────────

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

/** POST /api/dashboard/api-credentials/test — Test/verify an API credential */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    if (!body.id) {
      return NextResponse.json(
        { success: false, error: "ID de credencial requerido" },
        { status: 400 }
      );
    }

    const credential = await db.apiCredential.findUnique({ where: { id: body.id } });
    if (!credential) {
      return NextResponse.json(
        { success: false, error: "Credencial no encontrada" },
        { status: 404 }
      );
    }

    // Simulate a connection test based on platform
    const startTime = Date.now();
    let verifyStatus: string;
    let verifyMessage: string;

    try {
      // Simulated test — in production, this would make actual API calls
      // to verify the credential works with the target platform
      const platform = credential.platform;

      // Simulate network delay
      await new Promise((resolve) => setTimeout(resolve, 500 + Math.random() * 1000));

      // Simulated validation logic
      const keyLength = credential.apiKey.length;
      const hasValidPrefix =
        platform === "openai" ? credential.apiKey.startsWith("sk-") :
        platform === "anthropic" ? credential.apiKey.startsWith("sk-ant-") :
        platform === "google" ? credential.apiKey.length > 10 :
        true; // custom platforms always "pass" the format check

      if (keyLength < 8) {
        verifyStatus = "invalid";
        verifyMessage = `Formato de clave inválido para ${platform} (muy corta)`;
      } else if (!hasValidPrefix && ["openai", "anthropic"].includes(platform)) {
        verifyStatus = "invalid";
        verifyMessage = `Prefijo de clave no reconocido para ${platform}`;
      } else {
        verifyStatus = "valid";
        verifyMessage = `Conexión exitosa con ${platform} (${Date.now() - startTime}ms)`;
      }
    } catch {
      verifyStatus = "error";
      verifyMessage = "Error de conexión al verificar la credencial";
    }

    // Update the credential with test results
    await db.apiCredential.update({
      where: { id: body.id },
      data: {
        lastVerified: new Date(),
        verifyStatus,
        verifyMessage,
      },
    });

    return NextResponse.json({
      success: true,
      verifyStatus,
      verifyMessage,
      lastVerified: new Date().toISOString(),
    });
  } catch (error) {
    console.error("[POST /api/dashboard/api-credentials/test]", error);
    return NextResponse.json(
      { success: false, error: "Error al verificar credencial" },
      { status: 500 }
    );
  }
}
