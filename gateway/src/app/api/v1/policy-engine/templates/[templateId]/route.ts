// ─── Zenic-Agents v3 — Policy Engine API: Template CRUD ──────────────
// GET    /api/v1/policy-engine/templates/[templateId]  — Get a template
// PUT    /api/v1/policy-engine/templates/[templateId]  — Update a template
// DELETE /api/v1/policy-engine/templates/[templateId]  — Delete (deactivate) a template

import { NextRequest, NextResponse } from "next/server";
import { getTemplate, updateTemplate, deleteTemplate } from "@/lib/policy-engine";
import type { PolicyTemplate } from "@/lib/policy-engine";

// GET /api/v1/policy-engine/templates/[templateId]
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ templateId: string }> },
) {
  try {
    const { templateId } = await params;
    const record = await getTemplate(templateId);

    if (!record) {
      return NextResponse.json(
        { success: false, error: `Template "${templateId}" not found`, code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    return NextResponse.json({
      success: true,
      data: {
        templateId: record.templateId,
        name: record.name,
        version: record.version,
        description: record.description,
        category: record.category,
        industry: record.industry,
        tags: record.tags,
        parameters: record.parameters,
        documentTemplate: record.documentTemplate,
        defaults: record.defaults,
        constraints: record.constraints,
        generatedCount: record.generatedCount,
        isActive: record.isActive,
        author: record.author,
        contentHash: record.contentHash,
        createdAt: record.createdAt.toISOString(),
        updatedAt: record.updatedAt.toISOString(),
      },
    });
  } catch (error) {
    console.error("[PolicyEngine Template GET]", error);
    return NextResponse.json(
      { success: false, error: "Failed to get template", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

// PUT /api/v1/policy-engine/templates/[templateId]
export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ templateId: string }> },
) {
  try {
    const { templateId } = await params;
    const body = await request.json() as PolicyTemplate;

    const record = await updateTemplate(templateId, body);

    return NextResponse.json({
      success: true,
      data: {
        templateId: record.templateId,
        name: record.name,
        version: record.version,
        category: record.category,
        contentHash: record.contentHash,
        updatedAt: record.updatedAt.toISOString(),
      },
    });
  } catch (error) {
    if (error instanceof Error && error.name === "TemplateValidationError") {
      return NextResponse.json(
        { success: false, error: error.message, code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }
    console.error("[PolicyEngine Template PUT]", error);
    return NextResponse.json(
      { success: false, error: "Failed to update template", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

// DELETE /api/v1/policy-engine/templates/[templateId]
export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ templateId: string }> },
) {
  try {
    const { templateId } = await params;

    await deleteTemplate(templateId);

    return NextResponse.json({
      success: true,
      data: { templateId, deactivated: true },
    });
  } catch (error) {
    if (error instanceof Error && error.name === "TemplateValidationError") {
      return NextResponse.json(
        { success: false, error: error.message, code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }
    console.error("[PolicyEngine Template DELETE]", error);
    return NextResponse.json(
      { success: false, error: "Failed to delete template", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
