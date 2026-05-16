// ─── Zenic-Agents v3 — Policy Engine API: Namespace CRUD ─────────────
// GET    /api/v1/policy-engine/namespaces/[namespaceId]  — Get a namespace
// PUT    /api/v1/policy-engine/namespaces/[namespaceId]  — Update a namespace
// DELETE /api/v1/policy-engine/namespaces/[namespaceId]  — Delete (deactivate) a namespace

import { NextRequest, NextResponse } from "next/server";
import { getNamespace, updateNamespace, deleteNamespace } from "@/lib/policy-engine";
import type { NamespaceUpdateRequest } from "@/lib/policy-engine";

// GET /api/v1/policy-engine/namespaces/[namespaceId]
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ namespaceId: string }> },
) {
  try {
    const { namespaceId } = await params;
    const namespace = await getNamespace(namespaceId);

    if (!namespace) {
      return NextResponse.json(
        { success: false, error: `Namespace "${namespaceId}" not found`, code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    return NextResponse.json({
      success: true,
      data: namespace,
    });
  } catch (error) {
    console.error("[PolicyEngine Namespace GET]", error);
    return NextResponse.json(
      { success: false, error: "Failed to get namespace", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

// PUT /api/v1/policy-engine/namespaces/[namespaceId]
export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ namespaceId: string }> },
) {
  try {
    const { namespaceId } = await params;
    const body = await request.json() as NamespaceUpdateRequest;

    const namespace = await updateNamespace(namespaceId, body);

    return NextResponse.json({
      success: true,
      data: namespace,
    });
  } catch (error) {
    if (error instanceof Error && error.name === "NamespaceError") {
      return NextResponse.json(
        { success: false, error: error.message, code: (error as { code: string }).code },
        { status: 400 },
      );
    }
    console.error("[PolicyEngine Namespace PUT]", error);
    return NextResponse.json(
      { success: false, error: "Failed to update namespace", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

// DELETE /api/v1/policy-engine/namespaces/[namespaceId]
export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ namespaceId: string }> },
) {
  try {
    const { namespaceId } = await params;

    await deleteNamespace(namespaceId);

    return NextResponse.json({
      success: true,
      data: { namespaceId, deactivated: true },
    });
  } catch (error) {
    if (error instanceof Error && error.name === "NamespaceError") {
      return NextResponse.json(
        { success: false, error: error.message, code: (error as { code: string }).code },
        { status: 400 },
      );
    }
    console.error("[PolicyEngine Namespace DELETE]", error);
    return NextResponse.json(
      { success: false, error: "Failed to delete namespace", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
