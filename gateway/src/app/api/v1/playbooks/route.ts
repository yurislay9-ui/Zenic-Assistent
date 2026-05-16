// ─── Zenic-Agents v3 — Playbooks API: List + Create ──────────────────
// GET  /api/v1/playbooks          — List playbooks with optional filters
// POST /api/v1/playbooks          — Create a playbook (JSON or YAML)

import { NextRequest, NextResponse } from "next/server";
import {
  getPlaybookEngine,
  loadPlaybookFromYaml,
  compilePlaybookDocument,
} from "@/lib/playbooks";
import type { PlaybookDocument, Industry, CertificationStatus } from "@/lib/playbooks";

// GET /api/v1/playbooks
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const industry = searchParams.get("industry") as Industry | null;
    const certificationStatus = searchParams.get("certificationStatus") as CertificationStatus | null;
    const isActive = searchParams.get("isActive");
    const limit = Math.min(100, Math.max(1, Number(searchParams.get("limit")) || 50));
    const offset = Math.max(0, Number(searchParams.get("offset")) || 0);

    const engine = getPlaybookEngine();

    const filters: {
      industry?: Industry;
      certificationStatus?: CertificationStatus;
      isActive?: boolean;
    } = {};

    if (industry) {
      filters.industry = industry;
    }
    if (certificationStatus) {
      filters.certificationStatus = certificationStatus;
    }
    if (isActive !== null) {
      filters.isActive = isActive === "true";
    }

    const playbooks = await engine.listPlaybooks(filters);

    // Apply pagination
    const total = playbooks.length;
    const paginated = playbooks.slice(offset, offset + limit);

    const data = paginated.map((p) => ({
      playbookId: p.playbookId,
      name: p.name,
      nameEn: p.nameEn,
      industry: p.industry,
      subIndustry: p.subIndustry,
      version: p.version,
      description: p.description,
      icon: p.icon,
      color: p.color,
      certificationStatus: p.certificationStatus,
      isActive: p.isActive,
      capabilities: p.capabilities.length,
      policies: p.policies.length,
      contentHash: p.contentHash,
      createdAt: p.createdAt.toISOString(),
      updatedAt: p.updatedAt.toISOString(),
    }));

    return NextResponse.json({
      playbooks: data,
      total,
      limit,
      offset,
    });
  } catch (error) {
    console.error("[Playbooks v1 GET]", error);
    return NextResponse.json(
      { error: "Failed to fetch playbooks", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

// POST /api/v1/playbooks
export async function POST(request: NextRequest) {
  try {
    const contentType = request.headers.get("content-type") ?? "";
    let document: PlaybookDocument;
    let sourceYaml: string | undefined;

    if (contentType.includes("yaml") || contentType.includes("text/plain")) {
      // YAML input
      const yamlContent = await request.text();
      sourceYaml = yamlContent;
      document = loadPlaybookFromYaml(yamlContent);
    } else {
      // JSON input
      const body = await request.json();
      if (body.yaml) {
        sourceYaml = body.yaml;
        document = loadPlaybookFromYaml(body.yaml);
      } else if (body.document) {
        document = compilePlaybookDocument(body.document);
      } else if (body.apiVersion && body.kind && body.metadata) {
        document = compilePlaybookDocument(body as PlaybookDocument);
      } else {
        return NextResponse.json(
          { error: "Provide either a YAML string in 'yaml' field, a 'document' object, or a complete PlaybookDocument", code: "VALIDATION_ERROR" },
          { status: 400 },
        );
      }
    }

    const engine = getPlaybookEngine();
    const playbook = await engine.createPlaybook(document, sourceYaml);

    return NextResponse.json({
      playbook: {
        playbookId: playbook.playbookId,
        name: playbook.name,
        industry: playbook.industry,
        version: playbook.version,
        certificationStatus: playbook.certificationStatus,
        isActive: playbook.isActive,
        contentHash: playbook.contentHash,
        createdAt: playbook.createdAt.toISOString(),
      },
      message: `Playbook "${playbook.playbookId}" created successfully`,
    }, { status: 201 });
  } catch (error) {
    if (error instanceof Error && (error.name === "PlaybookValidationError" || error.name === "PlaybookCompilationError")) {
      return NextResponse.json(
        { error: error.message, code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }
    console.error("[Playbooks v1 POST]", error);
    return NextResponse.json(
      { error: "Failed to create playbook", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
