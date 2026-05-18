// ─── Zenic-Agents v3 — Compliance Map Service ──────────────────────────
// Split from compliance-map.ts — public API functions and internal helpers

import type { Industry, PlaybookCapability, PolicyReference } from "../types";
import { db } from "@/lib/db";
import type { ComplianceRequirement, StandardCoverage, PlaybookComplianceReport } from "./_types";
import { COMPLIANCE_STANDARDS } from "./_standards";
import { INDUSTRY_COMPLIANCE_MAP } from "./_industry-map";

// ─── Public Functions ──────────────────────────────────────────────────

/**
 * Get the compliance requirements for an industry.
 */
export function getIndustryComplianceRequirements(
  industry: Industry,
): ComplianceRequirement[] {
  const industryStr = industry as string;
  const requirements = INDUSTRY_COMPLIANCE_MAP[industryStr] ?? [];

  return requirements.map((req) => {
    const standardDef = COMPLIANCE_STANDARDS.find((s) => s.name === req.standard);
    const sections = standardDef
      ? Object.keys(standardDef.sections)
      : ["general"];

    return {
      standard: req.standard,
      sections,
      description: standardDef
        ? `Compliance with ${req.standard} (${Object.keys(standardDef.sections).length} sections)`
        : `Compliance with ${req.standard}`,
      mandatory: req.mandatory,
    };
  });
}

/**
 * Map a playbook to its compliance requirements and calculate coverage.
 * Visitor pattern: traverses the playbook's policies and capabilities.
 */
export async function mapPlaybookCompliance(
  playbookId: string,
): Promise<PlaybookComplianceReport> {
  const emptyReport = createEmptyReport(playbookId);

  try {
    const playbook = await db.playbook.findFirst({
      where: {
        OR: [
          { playbookId },
          { id: playbookId },
        ],
      },
    });

    if (!playbook) {
      emptyReport.gaps = [`Playbook not found: ${playbookId}`];
      return emptyReport;
    }

    const industry = playbook.industry;
    const capabilities: PlaybookCapability[] = JSON.parse(playbook.capabilities || "[]");
    const policyRefs: PolicyReference[] = JSON.parse(playbook.policies || "[]");

    const policyStatements = await loadPolicyStatements(policyRefs);
    const requiredStandards = getIndustryComplianceRequirements(industry as Industry);

    const standardCoverages: StandardCoverage[] = requiredStandards.map((req) => {
      const standardDef = COMPLIANCE_STANDARDS.find((s) => s.name === req.standard);

      if (!standardDef) {
        return {
          standard: req.standard,
          totalSections: req.sections.length,
          coveredSections: 0,
          coveragePct: 0,
          coveredBy: {},
          gaps: req.sections,
        };
      }

      const coveredBy: Record<string, string[]> = {};
      const gaps: string[] = [];

      for (const sectionRef of Object.keys(standardDef.sections)) {
        const section = standardDef.sections[sectionRef];

        const matchingCapabilities = capabilities.filter((cap) =>
          matchesKeywords(cap, section.capabilityKeywords),
        );

        const matchingPolicies = policyStatements.filter((stmt) =>
          matchesPolicyKeywords(stmt, section.keywords),
        );

        const coveringIds = [
          ...matchingCapabilities.map((c) => c.id),
          ...matchingPolicies.map((p) => p.policyId),
        ];

        if (coveringIds.length > 0) {
          coveredBy[sectionRef] = coveringIds;
        } else {
          gaps.push(sectionRef);
        }
      }

      const totalSections = Object.keys(standardDef.sections).length;
      const coveredSections = totalSections - gaps.length;
      const coveragePct = totalSections > 0
        ? Math.round((coveredSections / totalSections) * 100)
        : 0;

      return { standard: req.standard, totalSections, coveredSections, coveragePct, coveredBy, gaps };
    });

    const overallScore = calculateComplianceScore({
      ...emptyReport,
      playbookId: playbook.playbookId,
      playbookName: playbook.name,
      industry,
      requiredStandards,
      standards: standardCoverages,
      gaps: standardCoverages.flatMap((s) => s.gaps.map((g) => `${s.standard} §${g}`)),
      generatedAt: new Date().toISOString(),
    });

    return {
      playbookId: playbook.playbookId,
      playbookName: playbook.name,
      industry,
      requiredStandards,
      standards: standardCoverages,
      overallScore,
      gaps: standardCoverages.flatMap((s) => s.gaps.map((g) => `${s.standard} §${g}`)),
      generatedAt: new Date().toISOString(),
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    emptyReport.gaps = [`Error mapping compliance: ${message}`];
    return emptyReport;
  }
}

/**
 * Calculate a weighted compliance score from a report.
 * Mandatory standards carry 70% weight; optional standards carry 30%.
 */
export function calculateComplianceScore(
  report: PlaybookComplianceReport,
): number {
  if (report.standards.length === 0) return 0;

  const mandatoryStandards = report.standards.filter((s) => {
    const req = report.requiredStandards.find((r) => r.standard === s.standard);
    return req?.mandatory ?? true;
  });

  const optionalStandards = report.standards.filter((s) => {
    const req = report.requiredStandards.find((r) => r.standard === s.standard);
    return req?.mandatory === false;
  });

  const mandatoryScore = mandatoryStandards.length > 0
    ? mandatoryStandards.reduce((sum, s) => sum + s.coveragePct, 0) / mandatoryStandards.length
    : 0;

  const optionalScore = optionalStandards.length > 0
    ? optionalStandards.reduce((sum, s) => sum + s.coveragePct, 0) / optionalStandards.length
    : 100;

  const overallScore = Math.round(
    mandatoryStandards.length > 0 && optionalStandards.length > 0
      ? mandatoryScore * 0.7 + optionalScore * 0.3
      : mandatoryScore,
  );

  return Math.min(100, Math.max(0, overallScore));
}

/**
 * Format a compliance report as a human-readable string.
 */
export function formatComplianceReport(report: PlaybookComplianceReport): string {
  const lines: string[] = [
    "╔══════════════════════════════════════════════════════════════════╗",
    "║              Playbook Compliance Report                         ║",
    "╠══════════════════════════════════════════════════════════════════╣",
    `║  Playbook:  ${report.playbookName.padEnd(51)}║`,
    `║  ID:        ${report.playbookId.padEnd(51)}║`,
    `║  Industry:  ${report.industry.padEnd(51)}║`,
    `║  Score:     ${String(report.overallScore + "/100").padEnd(51)}║`,
    `║  Generated: ${report.generatedAt.padEnd(51)}║`,
    "╠══════════════════════════════════════════════════════════════════╣",
    "║  Standard Coverage                                              ║",
    "╠══════════════════════════════════════════════════════════════════╣",
  ];

  for (const std of report.standards) {
    const mandatory = report.requiredStandards.find((r) => r.standard === std.standard);
    const tag = mandatory?.mandatory ? "[MANDATORY]" : "[OPTIONAL] ";
    const bar = coverageBar(std.coveragePct);
    lines.push(
      `║  ${std.standard.padEnd(16)} ${tag} ${bar} ${String(std.coveragePct + "%").padEnd(5)}║`,
    );
    lines.push(
      `║    ${std.coveredSections}/${std.totalSections} sections covered${" ".repeat(Math.max(0, 41 - String(std.coveredSections + "/" + std.totalSections + " sections covered").length))}║`,
    );
    if (std.gaps.length > 0) {
      const gapStr = std.gaps.slice(0, 3).join(", ") +
        (std.gaps.length > 3 ? ` +${std.gaps.length - 3} more` : "");
      lines.push(`║    Gaps: ${gapStr.padEnd(55)}║`);
    }
  }

  if (report.gaps.length > 0) {
    lines.push("╠══════════════════════════════════════════════════════════════════╣");
    lines.push("║  Summary of Gaps                                                ║");
    lines.push("╠══════════════════════════════════════════════════════════════════╣");
    for (const gap of report.gaps.slice(0, 10)) {
      lines.push(`║  • ${gap.padEnd(61)}║`);
    }
    if (report.gaps.length > 10) {
      lines.push(`║  ... and ${report.gaps.length - 10} more gaps${" ".repeat(47)}║`);
    }
  }

  lines.push("╚══════════════════════════════════════════════════════════════════╝");
  return lines.join("\n");
}

// ─── Internal Helpers ──────────────────────────────────────────────────

function createEmptyReport(playbookId: string): PlaybookComplianceReport {
  return {
    playbookId,
    playbookName: "Unknown",
    industry: "unknown",
    requiredStandards: [],
    standards: [],
    overallScore: 0,
    gaps: [],
    generatedAt: new Date().toISOString(),
  };
}

async function loadPolicyStatements(
  policyRefs: PolicyReference[],
): Promise<Array<{ policyId: string; text: string }>> {
  if (policyRefs.length === 0) return [];

  try {
    const policyIds = policyRefs.map((ref) => ref.policyId);
    const policies = await db.declPolicy.findMany({
      where: { policyId: { in: policyIds } },
      select: { policyId: true, statements: true, compliance: true },
    });

    return policies.map((p) => ({
      policyId: p.policyId,
      text: [p.statements, p.compliance, p.policyId].join(" ").toLowerCase(),
    }));
  } catch {
    return [];
  }
}

function matchesKeywords(
  capability: PlaybookCapability,
  keywords: string[],
): boolean {
  const text = [capability.name, capability.description, capability.category, capability.id]
    .join(" ").toLowerCase();
  return keywords.some((kw) => text.includes(kw.toLowerCase()));
}

function matchesPolicyKeywords(
  policy: { policyId: string; text: string },
  keywords: string[],
): boolean {
  return keywords.some((kw) => policy.text.includes(kw.toLowerCase()));
}

function coverageBar(pct: number): string {
  const filled = Math.round(pct / 10);
  const empty = 10 - filled;
  return "█".repeat(filled) + "░".repeat(empty);
}
