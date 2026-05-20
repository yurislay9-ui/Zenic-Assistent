// ─── Zenic-Agents v3 — Playbook Compliance Mapper: Industry Mapping ────
// Maps industry identifiers to their required compliance standards.
// Industry keys align with the Industry enum values from types.ts
// and also support sub-industry aliases (e.g., "healthtech", "fintech").

import type { Industry } from "../types";
import type { ComplianceRequirement } from "./types";
import { COMPLIANCE_STANDARDS } from "./_standards";

// ─── Industry → Compliance Requirements Mapping ───────────────────────

/**
 * Maps industry identifiers to their required compliance standards.
 * Industry keys align with the Industry enum values from types.ts
 * and also support sub-industry aliases (e.g., "healthtech", "fintech").
 */
const INDUSTRY_COMPLIANCE_MAP: Record<string, Array<{
  standard: string;
  mandatory: boolean;
}>> = {
  // ─── Healthcare & HealthTech ──────────────────────────────
  healthcare: [
    { standard: "HIPAA", mandatory: true },
    { standard: "COPPA", mandatory: false },
    { standard: "HITECH", mandatory: true },
  ],
  healthtech: [
    { standard: "HIPAA", mandatory: true },
    { standard: "COPPA", mandatory: false },
    { standard: "HITECH", mandatory: true },
  ],

  // ─── Financial Services & FinTech ─────────────────────────
  financial_services: [
    { standard: "PCI-DSS", mandatory: true },
    { standard: "SOX", mandatory: true },
    { standard: "AML/KYC", mandatory: true },
    { standard: "GLBA", mandatory: true },
  ],
  fintech: [
    { standard: "PCI-DSS", mandatory: true },
    { standard: "SOX", mandatory: true },
    { standard: "AML/KYC", mandatory: true },
    { standard: "GLBA", mandatory: true },
  ],

  // ─── Education & EdTech ───────────────────────────────────
  education: [
    { standard: "FERPA", mandatory: true },
    { standard: "COPPA", mandatory: true },
  ],
  edtech: [
    { standard: "FERPA", mandatory: true },
    { standard: "COPPA", mandatory: true },
  ],

  // ─── Legal & LegalTech ────────────────────────────────────
  legal: [
    { standard: "ABA Model Rules", mandatory: true },
    { standard: "GDPR", mandatory: false },
  ],
  legaltech: [
    { standard: "ABA Model Rules", mandatory: true },
    { standard: "GDPR", mandatory: false },
  ],

  // ─── Retail ───────────────────────────────────────────────
  retail: [
    { standard: "PCI-DSS", mandatory: true },
    { standard: "GDPR", mandatory: false },
    { standard: "CCPA", mandatory: true },
  ],

  // ─── Manufacturing ────────────────────────────────────────
  manufacturing: [
    { standard: "ISO 27001", mandatory: true },
    { standard: "NIST", mandatory: false },
  ],

  // ─── Government ───────────────────────────────────────────
  government: [
    { standard: "FedRAMP", mandatory: true },
    { standard: "FISMA", mandatory: true },
    { standard: "NIST", mandatory: true },
  ],

  // ─── Insurance ────────────────────────────────────────────
  insurance: [
    { standard: "NAIC", mandatory: true },
    { standard: "SOX", mandatory: true },
    { standard: "GDPR", mandatory: false },
  ],

  // ─── Real Estate ──────────────────────────────────────────
  real_estate: [
    { standard: "GLBA", mandatory: true },
    { standard: "AML/KYC", mandatory: false },
  ],
  realestate: [
    { standard: "GLBA", mandatory: true },
    { standard: "AML/KYC", mandatory: false },
  ],

  // ─── Energy ───────────────────────────────────────────────
  energy: [
    { standard: "NERC CIP", mandatory: true },
    { standard: "ISO 27001", mandatory: false },
  ],

  // ─── Media ────────────────────────────────────────────────
  media: [
    { standard: "DMCA", mandatory: true },
    { standard: "GDPR", mandatory: false },
    { standard: "CCPA", mandatory: false },
  ],

  // ─── Logistics ────────────────────────────────────────────
  logistics: [
    { standard: "ISO 28000", mandatory: true },
    { standard: "C-TPAT", mandatory: false },
  ],

  // ─── Agriculture ──────────────────────────────────────────
  agriculture: [
    { standard: "FDA", mandatory: true },
    { standard: "USDA compliance", mandatory: true },
  ],

  // ─── Telecommunications ───────────────────────────────────
  telecommunications: [
    { standard: "FCC regulations", mandatory: true },
    { standard: "GDPR", mandatory: false },
  ],
  telecom: [
    { standard: "FCC regulations", mandatory: true },
    { standard: "GDPR", mandatory: false },
  ],

  // ─── Hospitality ──────────────────────────────────────────
  hospitality: [
    { standard: "PCI-DSS", mandatory: true },
    { standard: "GDPR", mandatory: false },
  ],

  // ─── Construction ─────────────────────────────────────────
  construction: [
    { standard: "OSHA", mandatory: true },
    { standard: "ISO 45001", mandatory: false },
  ],

  // ─── Automotive ───────────────────────────────────────────
  automotive: [
    { standard: "ISO 26262", mandatory: true },
    { standard: "TISAX", mandatory: false },
  ],

  // ─── Pharmaceutical ───────────────────────────────────────
  pharmaceutical: [
    { standard: "FDA 21 CFR Part 11", mandatory: true },
    { standard: "GxP", mandatory: true },
  ],

  // ─── Nonprofit ────────────────────────────────────────────
  nonprofit: [
    { standard: "IRS", mandatory: true },
    { standard: "State regulations", mandatory: true },
  ],

  // ─── Mining ───────────────────────────────────────────────
  mining: [
    { standard: "MSHA", mandatory: true },
    { standard: "ISO 14001", mandatory: false },
  ],

  // ─── Technology / SaaS ────────────────────────────────────
  technology: [
    { standard: "SOC 2", mandatory: true },
    { standard: "ISO 27001", mandatory: false },
    { standard: "GDPR", mandatory: false },
  ],
  saas: [
    { standard: "SOC 2", mandatory: true },
    { standard: "ISO 27001", mandatory: false },
    { standard: "GDPR", mandatory: false },
  ],

  // ─── Cybersecurity ────────────────────────────────────────
  cybersecurity: [
    { standard: "NIST", mandatory: true },
    { standard: "ISO 27001", mandatory: true },
    { standard: "CMMC", mandatory: false },
  ],

  // ─── Ecommerce ────────────────────────────────────────────
  ecommerce: [
    { standard: "PCI-DSS", mandatory: true },
    { standard: "GDPR", mandatory: false },
    { standard: "CCPA", mandatory: false },
  ],
};

// ─── Public Functions ──────────────────────────────────────────────────

/**
 * Get the compliance requirements for an industry.
 *
 * Maps the industry identifier to required compliance standards
 * using the predefined INDUSTRY_COMPLIANCE_MAP.
 *
 * @param industry - Industry identifier (from Industry enum or sub-industry alias)
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
