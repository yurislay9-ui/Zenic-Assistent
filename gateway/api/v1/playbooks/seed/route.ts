// ─── Zenic-Agents v3 — Playbooks API: Seed from YAML Templates ──────
// POST /api/v1/playbooks/seed — Seed playbooks from YAML templates directory

import { NextResponse } from "next/server";
import { readdir, readFile } from "fs/promises";
import { join } from "path";
import {
  loadPlaybookFromYaml,
  getPlaybookEngine,
} from "@/lib/playbooks";

// POST /api/v1/playbooks/seed
export async function POST() {
  try {
    const engine = getPlaybookEngine();
    const playbooksDir = join(process.cwd(), "playbooks");

    let files: string[];
    try {
      files = await readdir(playbooksDir);
    } catch {
      return NextResponse.json(
        { error: "Playbooks directory not found", code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    const yamlFiles = files.filter((f) => f.endsWith(".yaml") || f.endsWith(".yml"));

    if (yamlFiles.length === 0) {
      return NextResponse.json({
        seeded: 0,
        skipped: 0,
        errors: ["No YAML files found in playbooks directory"],
      });
    }

    let seeded = 0;
    let skipped = 0;
    const errors: string[] = [];

    for (const file of yamlFiles) {
      try {
        const filePath = join(playbooksDir, file);
        const yamlContent = await readFile(filePath, "utf-8");

        // Validate YAML by loading it
        const document = loadPlaybookFromYaml(yamlContent);

        // Check if playbookId already exists (upsert — skip if exists)
        const existing = await engine.getPlaybook(document.metadata.id);
        if (existing) {
          skipped++;
          continue;
        }

        // Create the playbook
        await engine.createPlaybook(document, yamlContent);
        seeded++;
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        errors.push(`${file}: ${message}`);
      }
    }

    return NextResponse.json({
      seeded,
      skipped,
      errors,
    });
  } catch (error) {
    console.error("[Playbooks Seed POST]", error);
    return NextResponse.json(
      { error: "Failed to seed playbooks", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
