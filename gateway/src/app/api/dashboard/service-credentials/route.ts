// ─── Service Credentials CRUD — Cifrado AES-256-GCM ─────────────────
// SECURITY: Los campos sensibles se cifran antes de persistir y se
// enmascaran antes de enviar al frontend. Nunca se usa localStorage.
// INVARIANT 4 — defensa en profundidad, la regla DENY es absoluta.

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { encrypt, decrypt, maskCredentialFields } from "@/lib/crypto";

/** GET /api/dashboard/service-credentials — Listar credenciales (enmascaradas) */
export async function GET() {
  try {
    const credentials = await db.serviceCredential.findMany({
      orderBy: { createdAt: "desc" },
    });

    const masked = credentials.map((cred) => {
      let campos: Record<string, string> = {};
      try {
        campos = decrypt({
          encryptedData: cred.encryptedData,
          iv: cred.iv,
          authTag: cred.authTag,
        });
      } catch {
        // Si la clave de cifrado cambió o los datos están corruptos,
        // mostrar campos vacíos en vez de fallar todo el endpoint.
        campos = { _error: "No se pudo descifrar — clave cambiada o datos corruptos" };
      }

      return {
        id: cred.id,
        serviceId: cred.serviceId,
        nombre: cred.nombre,
        campos: maskCredentialFields(campos),
        isActive: cred.isActive,
        createdAt: cred.createdAt.toISOString(),
        updatedAt: cred.updatedAt.toISOString(),
      };
    });

    return NextResponse.json({ success: true, credentials: masked });
  } catch (error) {
    console.error("[GET /api/dashboard/service-credentials]", error);
    return NextResponse.json(
      { success: false, error: "Error al obtener credenciales de servicio" },
      { status: 500 }
    );
  }
}

/** POST /api/dashboard/service-credentials — Crear credencial cifrada */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    // Validar campos obligatorios
    if (!body.serviceId || !body.nombre || !body.campos) {
      return NextResponse.json(
        { success: false, error: "serviceId, nombre y campos son obligatorios" },
        { status: 400 }
      );
    }

    // Validar que campos sea un objeto con al menos un valor
    const campos = body.campos as Record<string, string>;
    const hasValues = Object.values(campos).some((v) => typeof v === "string" && v.trim() !== "");
    if (!hasValues) {
      return NextResponse.json(
        { success: false, error: "Al menos un campo debe tener valor" },
        { status: 400 }
      );
    }

    // Cifrar los campos sensibles
    const encrypted = encrypt(campos);

    const credential = await db.serviceCredential.create({
      data: {
        serviceId: body.serviceId,
        nombre: body.nombre,
        encryptedData: encrypted.encryptedData,
        iv: encrypted.iv,
        authTag: encrypted.authTag,
        isActive: body.isActive !== undefined ? body.isActive : true,
      },
    });

    return NextResponse.json(
      {
        success: true,
        credential: {
          id: credential.id,
          serviceId: credential.serviceId,
          nombre: credential.nombre,
          campos: maskCredentialFields(campos),
          isActive: credential.isActive,
          createdAt: credential.createdAt.toISOString(),
          updatedAt: credential.updatedAt.toISOString(),
        },
      },
      { status: 201 }
    );
  } catch (error) {
    console.error("[POST /api/dashboard/service-credentials]", error);

    // Error específico para clave de cifrado faltante
    if (error instanceof Error && error.message.includes("ZENIC_ENCRYPTION_KEY")) {
      return NextResponse.json(
        { success: false, error: "Clave de cifrado no configurada en el servidor" },
        { status: 500 }
      );
    }

    return NextResponse.json(
      { success: false, error: "Error al crear credencial de servicio" },
      { status: 500 }
    );
  }
}

/** DELETE /api/dashboard/service-credentials — Eliminar credencial */
export async function DELETE(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const id = searchParams.get("id");

    if (!id) {
      return NextResponse.json(
        { success: false, error: "ID de credencial requerido" },
        { status: 400 }
      );
    }

    const existing = await db.serviceCredential.findUnique({ where: { id } });
    if (!existing) {
      return NextResponse.json(
        { success: false, error: "Credencial no encontrada" },
        { status: 404 }
      );
    }

    await db.serviceCredential.delete({ where: { id } });

    return NextResponse.json({ success: true, message: "Credencial de servicio eliminada" });
  } catch (error) {
    console.error("[DELETE /api/dashboard/service-credentials]", error);
    return NextResponse.json(
      { success: false, error: "Error al eliminar credencial de servicio" },
      { status: 500 }
    );
  }
}
