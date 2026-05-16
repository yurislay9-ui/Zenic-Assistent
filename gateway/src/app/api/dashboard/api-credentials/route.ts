// ─── API Credentials CRUD — List, Create, Update, Delete ──────────────

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

/** Mask a sensitive string showing only last N characters */
function mask(value: string | null | undefined, visibleChars = 4): string {
  if (!value) return "";
  if (value.length <= visibleChars) return value;
  return `${value.slice(0, 3)}...${value.slice(-visibleChars)}`;
}

/** Mask credential fields for safe UI display */
function maskCredential(cred: Record<string, unknown>) {
  return {
    ...cred,
    apiKey: mask(cred.apiKey as string),
    apiSecret: cred.apiSecret ? mask(cred.apiSecret as string) : null,
    password: cred.password ? mask(cred.password as string) : null,
  };
}

/** GET /api/dashboard/api-credentials — List all API credentials */
export async function GET() {
  try {
    const credentials = await db.apiCredential.findMany({
      orderBy: { createdAt: "desc" },
    });

    const masked = credentials.map((c) => maskCredential(c as Record<string, unknown>));

    return NextResponse.json({ success: true, credentials: masked });
  } catch (error) {
    console.error("[GET /api/dashboard/api-credentials]", error);
    return NextResponse.json(
      { success: false, error: "Error al obtener credenciales" },
      { status: 500 }
    );
  }
}

/** POST /api/dashboard/api-credentials — Create a new API credential */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    // Validate required fields
    if (!body.name || !body.platform || !body.apiKey) {
      return NextResponse.json(
        { success: false, error: "Nombre, plataforma y API Key son obligatorios" },
        { status: 400 }
      );
    }

    const credential = await db.apiCredential.create({
      data: {
        name: body.name,
        platform: body.platform,
        type: body.type || "api_key",
        apiKey: body.apiKey,
        apiSecret: body.apiSecret || null,
        endpoint: body.endpoint || null,
        username: body.username || null,
        password: body.password || null,
        scope: JSON.stringify(body.scope || []),
        isActive: body.isActive !== undefined ? body.isActive : true,
        metadata: JSON.stringify(body.metadata || {}),
      },
    });

    return NextResponse.json(
      { success: true, credential: maskCredential(credential as Record<string, unknown>) },
      { status: 201 }
    );
  } catch (error) {
    console.error("[POST /api/dashboard/api-credentials]", error);
    return NextResponse.json(
      { success: false, error: "Error al crear credencial" },
      { status: 500 }
    );
  }
}

/** PUT /api/dashboard/api-credentials — Update an API credential */
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

    // Build update data — only include fields that were provided
    const updateData: Record<string, unknown> = {};
    if (body.name !== undefined) updateData.name = body.name;
    if (body.platform !== undefined) updateData.platform = body.platform;
    if (body.type !== undefined) updateData.type = body.type;
    if (body.apiKey !== undefined) updateData.apiKey = body.apiKey;
    if (body.apiSecret !== undefined) updateData.apiSecret = body.apiSecret;
    if (body.endpoint !== undefined) updateData.endpoint = body.endpoint;
    if (body.username !== undefined) updateData.username = body.username;
    if (body.password !== undefined) updateData.password = body.password;
    if (body.scope !== undefined) updateData.scope = JSON.stringify(body.scope);
    if (body.isActive !== undefined) updateData.isActive = body.isActive;
    if (body.metadata !== undefined) updateData.metadata = JSON.stringify(body.metadata);

    const credential = await db.apiCredential.update({
      where: { id: body.id },
      data: updateData,
    });

    return NextResponse.json({
      success: true,
      credential: maskCredential(credential as Record<string, unknown>),
    });
  } catch (error) {
    console.error("[PUT /api/dashboard/api-credentials]", error);
    return NextResponse.json(
      { success: false, error: "Error al actualizar credencial" },
      { status: 500 }
    );
  }
}

/** DELETE /api/dashboard/api-credentials — Delete an API credential */
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
