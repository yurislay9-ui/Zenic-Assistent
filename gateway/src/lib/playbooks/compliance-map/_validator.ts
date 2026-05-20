// ─── Zenic-Agents v3 — Playbook Compliance Mapper: Validation & Reporting ─
// Visitor pattern: traverses playbook structure (capabilities + policies) to
// build compliance report, separating data from processing logic.
// Includes scoring, formatting, and internal helper functions.

import type {
  Industry,
  PlaybookCapability,
  PolicyReference,
} from "../types";
import type {
  ComplianceRequirement,
  StandardCoverage,
  PlaybookComplianceReport,
} from "./types";
import { COMPLIANCE_STANDARDS } from "./_standards";
import { getIndustryComplianceRequirements } from "./_mapper";
import { db } from "@/lib/db";

// ─── Public Functions ──────────────────────────────────────────────────

/**
 * Map a playbook to its compliance requirements and calculate coverage.
 *
 * Visitor pattern: traverses the playbook's policies and capabilities,
 * visiting each compliance standard section to check coverage.
 *
 * @param playbookId - Playbook ID to analyze (from DB)
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

    // Load referenced policies from DB for keyword analysis
    const policyStatements = await loadPolicyStatements(policyRefs);

    // Get industry compliance requirements
    const requiredStandards = getIndustryComplianceRequirements(industry as Industry);

    // Visitor: for each required standard, check coverage
    const standardCoverages: StandardCoverage[] = requiredStandards.map((req) => {
      const standardDef = COMPLIANCE_STANDARDS.find((s) => s.name === req.standard);

      if (!standardDef) {
        // Unknown standard — create minimal coverage entry
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

        // Visit capabilities for keyword matches
        const matchingCapabilities = capabilities.filter((cap) =>
          matchesKeywords(cap, section.capabilityKeywords),
        );

        // Visit policy statements for keyword matches
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

      return {
        standard: req.standard,
        totalSections,
        coveredSections,
        coveragePct,
        coveredBy,
        gaps,
      };
    });

    // Calculate overall score
    const overallScore = calculateComplianceScore({
      ...emptyReport,
      playbookId: playbook.playbookId,
      playbookName: playbook.name,
      industry,
      requiredStandards,
      standards: standardCoverages,
      gaps: standardCoverages.flatMap((s) =>
        s.gaps.map((g) => `${s.standard} §${g}`),
      ),
      generatedAt: new Date().toISOString(),
    });

    return {
      playbookId: playbook.playbookId,
      playbookName: playbook.name,
      industry,
      requiredStandards,
      standards: standardCoverages,
      overallScore,
      gaps: standardCoverages.flatMap((s) =>
        s.gaps.map((g) => `${s.standard} §${g}`),
      ),
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
 *
 * Mandatory standards carry 70% weight; optional standards carry 30%.
 * Returns a score from 0 to 100.
 *
 * @param report - The compliance report to score
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

  // Weighted average: mandatory 70%, optional 30%
  const mandatoryScore = mandatoryStandards.length > 0
    ? mandatoryStandards.reduce((sum, s) => sum + s.coveragePct, 0) / mandatoryStandards.length
    : 0;

  const optionalScore = optionalStandards.length > 0
    ? optionalStandards.reduce((sum, s) => sum + s.coveragePct, 0) / optionalStandards.length
    : 100; // No optional standards → full optional score

  const overallScore = Math.round(
    mandatoryStandards.length > 0 && optionalStandards.length > 0
      ? mandatoryScore * 0.7 + optionalScore * 0.3
      : mandatoryScore, // If no optional standards, use mandatory only
  );

  return Math.min(100, Math.max(0, overallScore));
}

/**
 * Format a compliance report as a human-readable string.
 *
 * @param report - The compliance report to format
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

/**
 * Create an empty compliance report for error/fallback cases.
 */
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

/**
 * Load policy statements from the database for keyword analysis.
 * Returns simplified objects with policyId and searchable text.
 */
async function loadPolicyStatements(
  policyRefs: PolicyReference[],
): Promise<Array<{ policyId: string; text: string }>> {
  if (policyRefs.length === 0) return [];

  try {
    const policyIds = policyRefs.map((ref) => ref.policyId);
    const policies = await db.declPolicy.findMany({
      where: {
        policyId: { in: policyIds },
      },
      select: {
        policyId: true,
        statements: true,
        compliance: true,
      },
    });

    return policies.map((p) => ({
      policyId: p.policyId,
      text: [
        p.statements,
        p.compliance,
        p.policyId,
      ].join(" ").toLowerCase(),
    }));
  } catch {
    return [];
  }
}

/**
 * Check if a capability matches any of the given keywords.
 * Visitor: visits capability name, description, and category.
 */
function matchesKeywords(
  capability: PlaybookCapability,
  keywords: string[],
): boolean {
  const text = [
    capability.name,
    capability.description,
    capability.category,
    capability.id,
  ].join(" ").toLowerCase();

  return keywords.some((kw) => text.includes(kw.toLowerCase()));
}

/**
 * Check if a policy's text content matches any of the given keywords.
 */
function matchesPolicyKeywords(
  policy: { policyId: string; text: string },
  keywords: string[],
): boolean {
  return keywords.some((kw) => policy.text.includes(kw.toLowerCase()));
}

/**
 * Generate a text-based coverage bar for visual representation.
 */
function coverageBar(pct: number): string {
  const filled = Math.round(pct / 10);
  const empty = 10 - filled;
  return "█".repeat(filled) + "░".repeat(empty);
}
