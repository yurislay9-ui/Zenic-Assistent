// ─── Zenic-Agents v3 — Playbooks API: Get/Update/Delete Playbook ─────
// GET    /api/v1/playbooks/[playbookId]   — Get a single playbook
// PUT    /api/v1/playbooks/[playbookId]   — Update a playbook (creates new version)
// DELETE /api/v1/playbooks/[playbookId]   — Deactivate a playbook (soft delete)

import { NextRequest, NextResponse } from "next/server";
import {
  getPlaybookEngine,
  compilePlaybookDocument,
  loadPlaybookFromYaml,
  calculateRoiFromPlaybook,
  mapPlaybookCompliance,
} from "@/lib/playbooks";
import type { PlaybookDocument } from "@/lib/playbooks";

// GET /api/v1/playbooks/[playbookId]
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ playbookId: string }> },
) {
  try {
    const { playbookId } = await params;
    const engine = getPlaybookEngine();
    const playbook = await engine.getPlaybook(playbookId);

    if (!playbook) {
      return NextResponse.json(
        { error: `Playbook "${playbookId}" not found`, code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    // Compute ROI for the playbook
    let roi = playbook.roiConfig.calculated ?? null;
    try {
      roi = await calculateRoiFromPlaybook(playbook.id);
    } catch {
      // Use pre-computed ROI if live calculation fails
    }

    // Compute compliance score
    let complianceScore: number | null = null;
    try {
      const complianceReport = await mapPlaybookCompliance(playbookId);
      complianceScore = complianceReport.overallScore;
    } catch {
      // Compliance score unavailable
    }

    return NextResponse.json({
      playbook: {
        ...playbook.document,
        roi: {
          ...playbook.roiConfig,
          calculated: roi,
        },
      },
      computed: {
        roi,
        complianceScore,
        isActive: playbook.isActive,
        certificationStatus: playbook.certificationStatus,
      },
    });
  } catch (error) {
    console.error("[Playbook GET by ID]", error);
    return NextResponse.json(
      { error: "Failed to fetch playbook", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

// PUT /api/v1/playbooks/[playbookId]
export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ playbookId: string }> },
) {
  try {
    const { playbookId } = await params;
    const engine = getPlaybookEngine();

    const existing = await engine.getPlaybook(playbookId);
    if (!existing) {
      return NextResponse.json(
        { error: `Playbook "${playbookId}" not found`, code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    const contentType = request.headers.get("content-type") ?? "";
    let document: PlaybookDocument;

    if (contentType.includes("yaml") || contentType.includes("text/plain")) {
      const yamlContent = await request.text();
      document = loadPlaybookFromYaml(yamlContent);
    } else {
      const body = await request.json();
      if (body.yaml) {
        document = loadPlaybookFromYaml(body.yaml);
      } else if (body.document) {
        document = compilePlaybookDocument(body.document);
      } else {
        return NextResponse.json(
          { error: "Provide either a YAML string in 'yaml' field or a 'document' object", code: "VALIDATION_ERROR" },
          { status: 400 },
        );
      }
    }

    if (document.metadata.id !== playbookId) {
      return NextResponse.json(
        { error: `Document metadata.id "${document.metadata.id}" does not match URL playbookId "${playbookId}"`, code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    const playbook = await engine.updatePlaybook(playbookId, document);

    return NextResponse.json({
      playbook: {
        playbookId: playbook.playbookId,
        name: playbook.name,
        version: playbook.version,
        contentHash: playbook.contentHash,
        certificationStatus: playbook.certificationStatus,
        updatedAt: playbook.updatedAt.toISOString(),
      },
      message: `Playbook "${playbookId}" updated successfully`,
    });
  } catch (error) {
    if (error instanceof Error && (error.name === "PlaybookValidationError" || error.name === "PlaybookCompilationError")) {
      return NextResponse.json(
        { error: error.message, code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }
    console.error("[Playbook PUT]", error);
    return NextResponse.json(
      { error: "Failed to update playbook", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

// DELETE /api/v1/playbooks/[playbookId]
export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ playbookId: string }> },
) {
  try {
    const { playbookId } = await params;
    const engine = getPlaybookEngine();

    const existing = await engine.getPlaybook(playbookId);
    if (!existing) {
      return NextResponse.json(
        { error: `Playbook "${playbookId}" not found`, code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    await engine.deactivatePlaybook(playbookId);

    return NextResponse.json({
      message: `Playbook "${playbookId}" deactivated successfully`,
    });
  } catch (error) {
    console.error("[Playbook DELETE]", error);
    return NextResponse.json(
      { error: "Failed to deactivate playbook", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
