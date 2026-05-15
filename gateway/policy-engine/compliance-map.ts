// ─── Zenic-Agents v3 — Compliance Mapper ──────────────────────────────
// Maps policy statements to compliance standards and calculates coverage.
// Supports PCI-DSS, HIPAA, SOX, GDPR, AML/KYC.
//
// Pattern: Visitor — traverses policy structure to build compliance report

import type {
  PolicyDocument,
  PolicyStatement,
  ComplianceMapping,
  ComplianceReport,
} from "./types";

// ─── Known Compliance Standards ────────────────────────────────────────

interface ComplianceStandard {
  name: string;
  sections: Record<string, {
    description: string;
    keywords: string[];
    resourcePatterns: string[];
  }>;
}

const STANDARDS: ComplianceStandard[] = [
  {
    name: "PCI-DSS",
    sections: {
      "1.2.3": { description: "Network configuration standards", keywords: ["network", "firewall", "configuration"], resourcePatterns: ["network/*", "firewall/*"] },
      "1.3.1": { description: "Restrict inbound traffic", keywords: ["traffic", "restrict", "inbound"], resourcePatterns: ["network/inbound"] },
      "2.1": { description: "Change default credentials", keywords: ["credential", "password", "default"], resourcePatterns: ["auth/*", "credential/*"] },
      "3.4": { description: "Render PAN unreadable", keywords: ["encrypt", "card", "pan", "data"], resourcePatterns: ["data/encrypt", "financial/*"] },
      "6.5": { description: "Address common vulnerabilities", keywords: ["vulnerability", "security", "input"], resourcePatterns: ["security/*", "validation/*"] },
      "7.1": { description: "Limit access to need-to-know", keywords: ["access", "restrict", "role"], resourcePatterns: ["access/*", "role/*", "permission/*"] },
      "7.2": { description: "Access control mechanism", keywords: ["rbac", "access", "control"], resourcePatterns: ["access/*", "policy/*"] },
      "8.1": { description: "Define user identification", keywords: ["user", "identity", "auth"], resourcePatterns: ["auth/*", "user/*"] },
      "8.3": { description: "Secure authentication", keywords: ["mfa", "authentication", "secure"], resourcePatterns: ["auth/mfa", "auth/*"] },
      "10.1": { description: "Implement audit trails", keywords: ["audit", "log", "trail"], resourcePatterns: ["audit/*", "log/*"] },
      "10.2": { description: "Automated audit trail", keywords: ["audit", "automated", "track"], resourcePatterns: ["audit/*"] },
    },
  },
  {
    name: "HIPAA",
    sections: {
      "164.312(a)": { description: "Access control", keywords: ["access", "control", "role"], resourcePatterns: ["access/*", "role/*", "health/*"] },
      "164.312(b)": { description: "Audit controls", keywords: ["audit", "log", "record"], resourcePatterns: ["audit/*", "log/*"] },
      "164.312(c)": { description: "Integrity controls", keywords: ["integrity", "protect", "modify"], resourcePatterns: ["data/*", "record/*"] },
      "164.312(d)": { description: "Person authentication", keywords: ["auth", "identity", "verify"], resourcePatterns: ["auth/*", "user/*"] },
      "164.312(e)": { description: "Transmission security", keywords: ["encrypt", "transmit", "secure"], resourcePatterns: ["network/*", "data/encrypt"] },
      "164.524": { description: "Access of PHI", keywords: ["phi", "access", "patient"], resourcePatterns: ["health/*", "patient/*"] },
      "164.530(j)": { description: "Retain documentation", keywords: ["retain", "document", "record"], resourcePatterns: ["audit/*", "record/*"] },
    },
  },
  {
    name: "SOX",
    sections: {
      "302": { description: "Corporate responsibility for reports", keywords: ["report", "financial", "responsibility"], resourcePatterns: ["financial/*", "report/*"] },
      "404": { description: "Internal control assessment", keywords: ["control", "internal", "assessment"], resourcePatterns: ["financial/*", "control/*", "policy/*"] },
      "409": { description: "Real-time issuer disclosure", keywords: ["disclosure", "real-time", "report"], resourcePatterns: ["financial/*", "report/*"] },
    },
  },
  {
    name: "GDPR",
    sections: {
      "5": { description: "Principles for processing", keywords: ["consent", "purpose", "minimize"], resourcePatterns: ["data/*", "consent/*"] },
      "6": { description: "Lawfulness of processing", keywords: ["lawful", "consent", "legal"], resourcePatterns: ["data/*", "consent/*"] },
      "17": { description: "Right to erasure", keywords: ["erase", "delete", "remove"], resourcePatterns: ["data/delete", "data/erase"] },
      "25": { description: "Data protection by design", keywords: ["design", "protect", "default"], resourcePatterns: ["data/*", "policy/*"] },
      "30": { description: "Records of processing", keywords: ["record", "processing", "log"], resourcePatterns: ["audit/*", "data/*"] },
      "32": { description: "Security of processing", keywords: ["security", "encrypt", "protect"], resourcePatterns: ["security/*", "data/encrypt"] },
      "35": { description: "Impact assessment", keywords: ["impact", "assessment", "risk"], resourcePatterns: ["risk/*", "assessment/*"] },
    },
  },
  {
    name: "AML/KYC",
    sections: {
      "3.1": { description: "Customer identification", keywords: ["identify", "customer", "verify"], resourcePatterns: ["customer/*", "identity/*"] },
      "3.2": { description: "Customer due diligence", keywords: ["due", "diligence", "risk"], resourcePatterns: ["customer/*", "risk/*"] },
      "3.3": { description: "Enhanced due diligence", keywords: ["enhanced", "high-risk", "pep"], resourcePatterns: ["customer/enhanced", "risk/*"] },
      "4.1": { description: "Transaction monitoring", keywords: ["transaction", "monitor", "suspicious"], resourcePatterns: ["financial/*", "transaction/*"] },
      "4.2": { description: "Suspicious activity reporting", keywords: ["suspicious", "report", "alert"], resourcePatterns: ["report/*", "alert/*"] },
    },
  },
];

// ─── Compliance Report Generation ─────────────────────────────────────

/**
 * Generate a compliance report for a policy document.
 * Maps statements to compliance standards and calculates coverage.
 */
export function generateComplianceReport(document: PolicyDocument): ComplianceReport {
  const policyId = document.metadata.id;
  const version = document.metadata.version;

  // Start with explicit compliance mappings from metadata
  const explicitMappings = document.metadata.compliance ?? [];

  // Auto-detect additional compliance mappings from statement content
  const autoMappings = autoDetectCompliance(document.statements);

  // Merge explicit and auto-detected
  const allStandards = mergeStandards(explicitMappings, autoMappings);

  // Build the report
  const standards = allStandards.map((std) => {
    const standardDef = STANDARDS.find((s) => s.name === std.standard);
    if (!standardDef) {
      return {
        name: std.standard,
        sections: std.sections.map((ref) => ({
          ref,
          statementIds: [],
          confidence: 0.5,
        })),
        coverage: 0,
      };
    }

    const mappedSections = std.sections.map((ref) => {
      const sectionDef = standardDef.sections[ref];
      const matchingStatements = findMatchingStatements(
        document.statements,
        sectionDef?.keywords ?? [],
        sectionDef?.resourcePatterns ?? [],
      );

      return {
        ref,
        statementIds: matchingStatements.map((s) => s.id),
        confidence: matchingStatements.length > 0
          ? Math.min(1, matchingStatements.length * 0.3 + 0.4)
          : (std.confidence ?? 0.3),
      };
    });

    const coveredCount = mappedSections.filter((s) => s.statementIds.length > 0).length;
    const coverage = mappedSections.length > 0 ? coveredCount / mappedSections.length : 0;

    return {
      name: std.standard,
      sections: mappedSections,
      coverage,
    };
  });

  // Calculate overall score
  const overallScore = standards.length > 0
    ? Math.round(standards.reduce((sum, s) => sum + s.coverage * 100, 0) / standards.length)
    : 0;

  // Find gaps (sections without matching statements)
  const gaps: string[] = [];
  for (const std of standards) {
    for (const section of std.sections) {
      if (section.statementIds.length === 0) {
        gaps.push(`${std.name} §${section.ref}`);
      }
    }
  }

  return {
    policyId,
    version,
    standards,
    overallScore,
    gaps,
  };
}

/**
 * Auto-detect compliance standards from statement content.
 */
function autoDetectCompliance(
  statements: PolicyStatement[],
): ComplianceMapping[] {
  const mappings: Map<string, ComplianceMapping> = new Map();

  for (const statement of statements) {
    const text = [
      statement.description ?? "",
      statement.resource,
      statement.action,
      ...(statement.tags ?? []),
    ].join(" ").toLowerCase();

    for (const standard of STANDARDS) {
      const matchedSections: string[] = [];

      for (const [ref, section] of Object.entries(standard.sections)) {
        const hasKeyword = section.keywords.some((kw) => text.includes(kw.toLowerCase()));
        const hasPattern = section.resourcePatterns.some((pat) =>
          matchesResourcePattern(pat, statement.resource),
        );

        if (hasKeyword || hasPattern) {
          matchedSections.push(ref);
        }
      }

      if (matchedSections.length > 0) {
        const existing = mappings.get(standard.name);
        if (existing) {
          const merged = new Set([...existing.sections, ...matchedSections]);
          mappings.set(standard.name, {
            standard: standard.name,
            sections: [...merged],
            confidence: Math.min(1, existing.confidence ?? 0.5 + matchedSections.length * 0.1),
          });
        } else {
          mappings.set(standard.name, {
            standard: standard.name,
            sections: matchedSections,
            confidence: 0.6,
          });
        }
      }
    }
  }

  return [...mappings.values()];
}

function findMatchingStatements(
  statements: PolicyStatement[],
  keywords: string[],
  resourcePatterns: string[],
): PolicyStatement[] {
  return statements.filter((stmt) => {
    const text = [stmt.description ?? "", stmt.resource, stmt.action].join(" ").toLowerCase();
    const hasKeyword = keywords.some((kw) => text.includes(kw.toLowerCase()));
    const hasPattern = resourcePatterns.some((pat) => matchesResourcePattern(pat, stmt.resource));
    return hasKeyword || hasPattern;
  });
}

function matchesResourcePattern(pattern: string, resource: string): boolean {
  if (pattern === resource) return true;
  if (pattern.endsWith("/*")) {
    const prefix = pattern.slice(0, -2);
    return resource.startsWith(`${prefix}/`) || resource === prefix;
  }
  return false;
}

function mergeStandards(
  explicit: ComplianceMapping[],
  autoDetected: ComplianceMapping[],
): Array<ComplianceMapping & { confidence: number }> {
  const merged = new Map<string, ComplianceMapping & { confidence: number }>();

  for (const m of explicit) {
    merged.set(m.standard, { ...m, confidence: m.confidence ?? 0.9 });
  }

  for (const m of autoDetected) {
    const existing = merged.get(m.standard);
    if (existing) {
      const mergedSections = new Set([...existing.sections, ...m.sections]);
      merged.set(m.standard, {
        ...existing,
        sections: [...mergedSections],
        confidence: Math.max(existing.confidence, m.confidence ?? 0.6),
      });
    } else {
      merged.set(m.standard, { ...m, confidence: m.confidence ?? 0.6 });
    }
  }

  return [...merged.values()];
}
