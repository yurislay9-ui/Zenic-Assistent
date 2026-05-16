// ─── Zenic-Agents v3 — Policy Engine API: Seed ───────────────────────
// POST /api/v1/policies/seed — Seed default policies from YAML files

import { NextResponse } from "next/server";
import { readFile, readdir, access } from "fs/promises";
import { join } from "path";
import { db } from "@/lib/db";
import { loadPolicyFromYaml, computeContentHash } from "@/lib/policy-engine";
import type { PolicyDocument } from "@/lib/policy-engine";

// POST /api/v1/policies/seed
export async function POST() {
  try {
    const policiesDir = join(process.cwd(), "policies");
    const results: Array<{ policyId: string; action: string; version: string }> = [];

    // Check if policies directory exists
    try {
      await access(policiesDir);
    } catch {
      return NextResponse.json({
        success: true,
        data: { seeded: 0, message: "No policies directory found" },
      });
    }

    // Read YAML files
    const allFiles = await readdir(policiesDir);
    const yamlFiles = allFiles.filter((f) => f.endsWith(".yaml") || f.endsWith(".yml"));

    for (const file of yamlFiles) {
      try {
        const yamlContent = await readFile(join(policiesDir, file), "utf-8");
        const document = loadPolicyFromYaml(yamlContent);
        const contentHash = computeContentHash(document);
        const policyId = document.metadata.id;

        // Upsert: create or update
        const existing = await db.declPolicy.findUnique({ where: { policyId } });

        if (existing) {
          // Only update if content changed
          if (existing.contentHash !== contentHash) {
            await db.declPolicy.update({
              where: { policyId },
              data: {
                name: document.metadata.name,
                description: document.metadata.description,
                version: document.metadata.version,
                labels: JSON.stringify(document.metadata.labels ?? {}),
                compliance: JSON.stringify(document.metadata.compliance ?? []),
                statements: JSON.stringify(document.statements),
                tests: JSON.stringify(document.tests ?? []),
                sourceYaml: yamlContent,
                contentHash,
                author: document.metadata.author ?? null,
                isActive: true,
              },
            });

            // Create new version
            const policy = await db.declPolicy.findUnique({ where: { policyId } });
            if (policy) {
              await db.declPolicyVersion.create({
                data: {
                  declPolicyId: policy.id,
                  version: document.metadata.version,
                  contentHash,
                  document: JSON.stringify(document),
                  status: "active",
                  createdBy: "seed",
                  changeDescription: `Seeded from ${file}`,
                  parentVersionId: null,
                },
              });
            }

            results.push({ policyId, action: "updated", version: document.metadata.version });
          } else {
            results.push({ policyId, action: "unchanged", version: document.metadata.version });
          }
        } else {
          const policy = await db.declPolicy.create({
            data: {
              policyId,
              name: document.metadata.name,
              description: document.metadata.description,
              version: document.metadata.version,
              labels: JSON.stringify(document.metadata.labels ?? {}),
              compliance: JSON.stringify(document.metadata.compliance ?? []),
              statements: JSON.stringify(document.statements),
              tests: JSON.stringify(document.tests ?? []),
              sourceYaml: yamlContent,
              contentHash,
              author: document.metadata.author ?? null,
            },
          });

          // Create initial version
          await db.declPolicyVersion.create({
            data: {
              declPolicyId: policy.id,
              version: document.metadata.version,
              contentHash,
              document: JSON.stringify(document),
              status: "active",
              createdBy: "seed",
              changeDescription: `Initial seed from ${file}`,
              parentVersionId: null,
            },
          });

          results.push({ policyId, action: "created", version: document.metadata.version });
        }
      } catch (err) {
        console.error(`[Seed] Failed to load ${file}:`, err);
        results.push({ policyId: file, action: "error", version: "n/a" });
      }
    }

    return NextResponse.json({
      success: true,
      data: {
        totalFiles: yamlFiles.length,
        results,
      },
    });
  } catch (error) {
    console.error("[Policy Seed POST]", error);
    return NextResponse.json(
      { success: false, error: "Failed to seed policies", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
