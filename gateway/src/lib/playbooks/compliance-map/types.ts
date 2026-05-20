// ─── Zenic-Agents v3 — Playbook Compliance Mapper: Types ────────────────
// Exported interfaces for the compliance mapping system.

// ─── Exported Types ────────────────────────────────────────────────────

/** A single compliance requirement for an industry */
export interface ComplianceRequirement {
  /** Compliance standard name (e.g., "HIPAA", "PCI-DSS") */
  standard: string;
  /** Relevant sections of the standard */
  sections: string[];
  /** Human-readable description of the requirement */
  description: string;
  /** Whether this requirement is mandatory for the industry */
  mandatory: boolean;
}

/** Per-standard coverage breakdown within a compliance report */
export interface StandardCoverage {
  /** Compliance standard name */
  standard: string;
  /** Total sections required */
  totalSections: number;
  /** Number of sections covered by playbook policies/capabilities */
  coveredSections: number;
  /** Coverage percentage (0-100) */
  coveragePct: number;
  /** Maps section ID to policy IDs that address it */
  coveredBy: Record<string, string[]>;
  /** Sections not covered by any policy or capability */
  gaps: string[];
}

/** Complete compliance report for a playbook */
export interface PlaybookComplianceReport {
  /** Playbook ID */
  playbookId: string;
  /** Playbook name */
  playbookName: string;
  /** Industry of the playbook */
  industry: string;
  /** Compliance standards required for this industry */
  requiredStandards: ComplianceRequirement[];
  /** Per-standard coverage breakdown */
  standards: StandardCoverage[];
  /** Overall compliance score (0-100, weighted average) */
  overallScore: number;
  /** All uncovered sections across all standards */
  gaps: string[];
  /** When this report was generated */
  generatedAt: string;
}
