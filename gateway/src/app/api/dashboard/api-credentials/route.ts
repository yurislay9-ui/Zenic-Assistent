// ─── API Credentials CRUD — Cifrado AES-256-GCM ─────────────────────
// SECURITY: Los campos sensibles (apiKey, apiSecret, password, username)
// se cifran antes de persistir y se enmascaran antes de enviar al frontend.
// INVARIANT 4 — defensa en profundidad, la regla DENY es absoluta.

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { encrypt, decrypt, maskCredentialFields } from "@/lib/crypto";

/** Campos sensibles que se cifran como un blob JSON */
interface SensitiveFields {
  apiKey: string;
  apiSecret?: string | null;
  password?: string | null;
  username?: string | null;
}

/** Whitelist de campos permitidos en POST */
const POST_ALLOWED_FIELDS = new Set([
  "name", "platform", "type", "apiKey", "apiSecret",
  "endpoint", "username", "password", "scope", "isActive", "metadata",
]);

/** Whitelist de campos permitidos en PUT */
const PUT_ALLOWED_FIELDS = new Set([
  "name", "platform", "type", "apiKey", "apiSecret",
  "endpoint", "username", "password", "scope", "isActive", "metadata",
]);

/** GET /api/dashboard/api-credentials — Listar credenciales (enmascaradas) */
export async function GET() {
  try {
    const credentials = await db.apiCredential.findMany({
      orderBy: { createdAt: "desc" },
    });

    const masked = credentials.map((cred) => {
      let sensitive: SensitiveFields = { apiKey: "" };
      try {
        sensitive = decrypt({
          encryptedData: cred.encryptedData,
          iv: cred.iv,
          authTag: cred.authTag,
        }) as unknown as SensitiveFields;
      } catch {
        // Si la clave de cifrado cambió o los datos están corruptos,
        // mostrar campos vacíos en vez de fallar todo el endpoint.
        sensitive = { apiKey: "", _error: "No se pudo descifrar" } as unknown as SensitiveFields;
      }

      return {
        id: cred.id,
        name: cred.name,
        platform: cred.platform,
        type: cred.type,
        endpoint: cred.endpoint,
        scope: JSON.parse(cred.scope || "[]"),
        isActive: cred.isActive,
        lastVerified: cred.lastVerified?.toISOString() ?? null,
        verifyStatus: cred.verifyStatus,
        verifyMessage: cred.verifyMessage,
        metadata: JSON.parse(cred.metadata || "{}"),
        createdAt: cred.createdAt.toISOString(),
        updatedAt: cred.updatedAt.toISOString(),
        // Campos sensibles enmascarados
        apiKey: maskCredentialFields({ apiKey: sensitive.apiKey || "" }).apiKey,
        apiSecret: sensitive.apiSecret
          ? maskCredentialFields({ apiSecret: sensitive.apiSecret }).apiSecret
          : null,
        username: sensitive.username ?? null,
        password: sensitive.password
          ? maskCredentialFields({ password: sensitive.password }).password
          : null,
      };
    });

    return NextResponse.json({ success: true, credentials: masked });
  } catch (error) {
    console.error("[GET /api/dashboard/api-credentials]", error);
    return NextResponse.json(
      { success: false, error: "Error al obtener credenciales" },
      { status: 500 }
    );
  }
}

/** POST /api/dashboard/api-credentials — Crear credencial cifrada */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    // Validar campos obligatorios
    if (!body.name || !body.platform || !body.apiKey) {
      return NextResponse.json(
        { success: false, error: "Nombre, plataforma y API Key son obligatorios" },
        { status: 400 }
      );
    }

    // Filtrar solo campos permitidos (whitelist)
    const filtered: Record<string, unknown> = {};
    for (const key of Object.keys(body)) {
      if (POST_ALLOWED_FIELDS.has(key)) {
        filtered[key] = body[key];
      }
    }

    // Cifrar campos sensibles
    const sensitive: SensitiveFields = {
      apiKey: String(filtered.apiKey || ""),
      apiSecret: filtered.apiSecret ? String(filtered.apiSecret) : null,
      password: filtered.password ? String(filtered.password) : null,
      username: filtered.username ? String(filtered.username) : null,
    };
    const encrypted = encrypt(sensitive as unknown as Record<string, string>);

    const credential = await db.apiCredential.create({
      data: {
        name: String(filtered.name),
        platform: String(filtered.platform),
        type: String(filtered.type || "api_key"),
        encryptedData: encrypted.encryptedData,
        iv: encrypted.iv,
        authTag: encrypted.authTag,
        endpoint: filtered.endpoint ? String(filtered.endpoint) : null,
        scope: JSON.stringify(filtered.scope || []),
        isActive: filtered.isActive !== undefined ? Boolean(filtered.isActive) : true,
        metadata: JSON.stringify(filtered.metadata || {}),
      },
    });

    return NextResponse.json(
      {
        success: true,
        credential: {
          id: credential.id,
          name: credential.name,
          platform: credential.platform,
          type: credential.type,
          endpoint: credential.endpoint,
          scope: JSON.parse(credential.scope || "[]"),
          isActive: credential.isActive,
          verifyStatus: credential.verifyStatus,
          metadata: JSON.parse(credential.metadata || "{}"),
          createdAt: credential.createdAt.toISOString(),
          updatedAt: credential.updatedAt.toISOString(),
          // Solo mostrar enmascarado
          apiKey: maskCredentialFields({ apiKey: sensitive.apiKey }).apiKey,
          apiSecret: sensitive.apiSecret
            ? maskCredentialFields({ apiSecret: sensitive.apiSecret }).apiSecret
            : null,
          username: sensitive.username ?? null,
          password: sensitive.password
            ? maskCredentialFields({ password: sensitive.password }).password
            : null,
        },
      },
      { status: 201 }
    );
  } catch (error) {
    console.error("[POST /api/dashboard/api-credentials]", error);

    if (error instanceof Error && error.message.includes("ZENIC_ENCRYPTION_KEY")) {
      return NextResponse.json(
        { success: false, error: "Clave de cifrado no configurada en el servidor" },
        { status: 500 }
      );
    }

    return NextResponse.json(
      { success: false, error: "Error al crear credencial" },
      { status: 500 }
    );
  }
}

/** PUT /api/dashboard/api-credentials — Actualizar credencial */
export async function PUT(request: NextRequest) {
  try {
    const body = await request.json();

    if (!body.id) {
      return NextResponse.json(
        { success: false, error: "ID de credencial requerido" },
        { status: 400 }
      );
    }

    const existing = await db.apiCredential.findUnique({ where: { id: body.id } });
    if (!existing) {
      return NextResponse.json(
        { success: false, error: "Credencial no encontrada" },
        { status: 404 }
      );
    }

    // Construir datos de actualización — solo campos permitidos (whitelist)
    const updateData: Record<string, unknown> = {};

    // Campos no sensibles
    if (body.name !== undefined) updateData.name = String(body.name);
    if (body.platform !== undefined) updateData.platform = String(body.platform);
    if (body.type !== undefined) updateData.type = String(body.type);
    if (body.endpoint !== undefined) updateData.endpoint = body.endpoint ? String(body.endpoint) : null;
    if (body.scope !== undefined) updateData.scope = JSON.stringify(body.scope);
    if (body.isActive !== undefined) updateData.isActive = Boolean(body.isActive);
    if (body.metadata !== undefined) updateData.metadata = JSON.stringify(body.metadata);

    // Si algún campo sensible cambió, hay que re-cifrar
    const hasSensitiveUpdate =
      body.apiKey !== undefined ||
      body.apiSecret !== undefined ||
      body.password !== undefined ||
      body.username !== undefined;

    if (hasSensitiveUpdate) {
      // Descifrar existentes para mezclar con nuevos valores
      let currentSensitive: SensitiveFields = { apiKey: "" };
      try {
        currentSensitive = decrypt({
          encryptedData: existing.encryptedData,
          iv: existing.iv,
          authTag: existing.authTag,
        }) as unknown as SensitiveFields;
      } catch {
        // Si no se puede descifrar, empezar con campos vacíos
        currentSensitive = { apiKey: "" };
      }

      // Mezclar: nuevos valores sobreescriben existentes
      const merged: SensitiveFields = {
        apiKey: body.apiKey !== undefined ? String(body.apiKey) : (currentSensitive.apiKey || ""),
        apiSecret: body.apiSecret !== undefined
          ? (body.apiSecret ? String(body.apiSecret) : null)
          : currentSensitive.apiSecret,
        password: body.password !== undefined
          ? (body.password ? String(body.password) : null)
          : currentSensitive.password,
        username: body.username !== undefined
          ? (body.username ? String(body.username) : null)
          : currentSensitive.username,
      };

      const encrypted = encrypt(merged as unknown as Record<string, string>);
      updateData.encryptedData = encrypted.encryptedData;
      updateData.iv = encrypted.iv;
      updateData.authTag = encrypted.authTag;
    }

    const credential = await db.apiCredential.update({
      where: { id: body.id },
      data: updateData,
    });

    // Descifrar para enmascarar en la respuesta
    let responseSensitive: SensitiveFields = { apiKey: "" };
    try {
      responseSensitive = decrypt({
        encryptedData: credential.encryptedData,
        iv: credential.iv,
        authTag: credential.authTag,
      }) as unknown as SensitiveFields;
    } catch {
      responseSensitive = { apiKey: "" };
    }

    return NextResponse.json({
      success: true,
      credential: {
        id: credential.id,
        name: credential.name,
        platform: credential.platform,
        type: credential.type,
        endpoint: credential.endpoint,
        scope: JSON.parse(credential.scope || "[]"),
        isActive: credential.isActive,
        verifyStatus: credential.verifyStatus,
        verifyMessage: credential.verifyMessage,
        metadata: JSON.parse(credential.metadata || "{}"),
        createdAt: credential.createdAt.toISOString(),
        updatedAt: credential.updatedAt.toISOString(),
        apiKey: maskCredentialFields({ apiKey: responseSensitive.apiKey || "" }).apiKey,
        apiSecret: responseSensitive.apiSecret
          ? maskCredentialFields({ apiSecret: responseSensitive.apiSecret }).apiSecret
          : null,
        username: responseSensitive.username ?? null,
        password: responseSensitive.password
          ? maskCredentialFields({ password: responseSensitive.password }).password
          : null,
      },
    });
  } catch (error) {
    console.error("[PUT /api/dashboard/api-credentials]", error);

    if (error instanceof Error && error.message.includes("ZENIC_ENCRYPTION_KEY")) {
      return NextResponse.json(
        { success: false, error: "Clave de cifrado no configurada en el servidor" },
        { status: 500 }
      );
    }

    return NextResponse.json(
      { success: false, error: "Error al actualizar credencial" },
      { status: 500 }
    );
  }
}

/** DELETE /api/dashboard/api-credentials — Eliminar credencial */
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

    const existing = await db.apiCredential.findUnique({ where: { id } });
    if (!existing) {
      return NextResponse.json(
        { success: false, error: "Credencial no encontrada" },
        { status: 404 }
      );
    }

    await db.apiCredential.delete({ where: { id } });

    return NextResponse.json({ success: true, message: "Credencial eliminada" });
  } catch (error) {
    console.error("[DELETE /api/dashboard/api-credentials]", error);
    return NextResponse.json(
      { success: false, error: "Error al eliminar credencial" },
      { status: 500 }
    );
  }
}
