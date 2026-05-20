// ─── Zenic-Agents v3 — Playbook Compliance Mapper: Public API ──────────
// Re-exports everything from the compliance-map subdirectory.
// All symbols importable from the original compliance-map.ts remain
// importable from "./compliance-map" (this index resolves the directory).

// Types
export type {
  ComplianceRequirement,
  StandardCoverage,
  PlaybookComplianceReport,
} from "./types";

// Functions
export {
  getIndustryComplianceRequirements,
} from "./_mapper";

export {
  mapPlaybookCompliance,
  calculateComplianceScore,
  formatComplianceReport,
} from "./_validator";
