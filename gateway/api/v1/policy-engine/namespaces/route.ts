// ─── Zenic-Agents v3 — Policy Engine API: Namespace List + Create ─────
// GET  /api/v1/policy-engine/namespaces          — List namespaces
// POST /api/v1/policy-engine/namespaces          — Create a namespace

import { NextRequest, NextResponse } from "next/server";
import { listNamespaces, createNamespace } from "@/lib/policy-engine";
import type { PolicyNamespace } from "@/lib/policy-engine";

// GET /api/v1/policy-engine/namespaces
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const tenantId = searchParams.get("tenantId") ?? undefined;
    const parentNamespaceId = searchParams.get("parentNamespaceId") ?? undefined;

    const namespaces = await listNamespaces(tenantId, parentNamespaceId);

    const data = namespaces.map((ns) => ({
      namespaceId: ns.metadata.id,
      name: ns.metadata.name,
      description: ns.metadata.description,
      tenantId: ns.metadata.tenantId,
      parentNamespaceId: ns.metadata.parentNamespaceId ?? null,
      path: ns.metadata.path,
      resolutionStrategy: ns.resolutionStrategy,
      isolationLevel: ns.isolationLevel,
      inheritFromParent: ns.hierarchy.inheritFromParent,
      createdAt: ns.metadata.createdAt,
      updatedAt: ns.metadata.updatedAt,
    }));

    return NextResponse.json({
      success: true,
      data,
      total: data.length,
    });
  } catch (error) {
    console.error("[PolicyEngine Namespaces GET]", error);
    return NextResponse.json(
      { success: false, error: "Failed to list namespaces", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

// POST /api/v1/policy-engine/namespaces
export async function POST(request: NextRequest) {
  try {
    const body = await request.json() as PolicyNamespace;

    const namespace = await createNamespace(body);

    return NextResponse.json({
      success: true,
      data: namespace,
    }, { status: 201 });
  } catch (error) {
    if (error instanceof Error && error.name === "NamespaceError") {
      const code = (error as { code: string }).code;
      const status = code === "DUPLICATE_NAMESPACE_ID" ? 409 : 400;
      return NextResponse.json(
        { success: false, error: error.message, code },
        { status },
      );
    }
    console.error("[PolicyEngine Namespaces POST]", error);
    return NextResponse.json(
      { success: false, error: "Failed to create namespace", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
