// ─── Zenic-Agents v3 — Industry Compliance Map ─────────────────────────
// Split from compliance-map.ts — INDUSTRY_COMPLIANCE_MAP constant

export const INDUSTRY_COMPLIANCE_MAP: Record<string, Array<{
  standard: string;
  mandatory: boolean;
}>> = {
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
  education: [
    { standard: "FERPA", mandatory: true },
    { standard: "COPPA", mandatory: true },
  ],
  edtech: [
    { standard: "FERPA", mandatory: true },
    { standard: "COPPA", mandatory: true },
  ],
  legal: [
    { standard: "ABA Model Rules", mandatory: true },
    { standard: "GDPR", mandatory: false },
  ],
  legaltech: [
    { standard: "ABA Model Rules", mandatory: true },
    { standard: "GDPR", mandatory: false },
  ],
  retail: [
    { standard: "PCI-DSS", mandatory: true },
    { standard: "GDPR", mandatory: false },
    { standard: "CCPA", mandatory: true },
  ],
  manufacturing: [
    { standard: "ISO 27001", mandatory: true },
    { standard: "NIST", mandatory: false },
  ],
  government: [
    { standard: "FedRAMP", mandatory: true },
    { standard: "FISMA", mandatory: true },
    { standard: "NIST", mandatory: true },
  ],
  insurance: [
    { standard: "NAIC", mandatory: true },
    { standard: "SOX", mandatory: true },
    { standard: "GDPR", mandatory: false },
  ],
  real_estate: [
    { standard: "GLBA", mandatory: true },
    { standard: "AML/KYC", mandatory: false },
  ],
  realestate: [
    { standard: "GLBA", mandatory: true },
    { standard: "AML/KYC", mandatory: false },
  ],
  energy: [
    { standard: "NERC CIP", mandatory: true },
    { standard: "ISO 27001", mandatory: false },
  ],
  media: [
    { standard: "DMCA", mandatory: true },
    { standard: "GDPR", mandatory: false },
    { standard: "CCPA", mandatory: false },
  ],
  logistics: [
    { standard: "ISO 28000", mandatory: true },
    { standard: "C-TPAT", mandatory: false },
  ],
  agriculture: [
    { standard: "FDA", mandatory: true },
    { standard: "USDA compliance", mandatory: true },
  ],
  telecommunications: [
    { standard: "FCC regulations", mandatory: true },
    { standard: "GDPR", mandatory: false },
  ],
  telecom: [
    { standard: "FCC regulations", mandatory: true },
    { standard: "GDPR", mandatory: false },
  ],
  hospitality: [
    { standard: "PCI-DSS", mandatory: true },
    { standard: "GDPR", mandatory: false },
  ],
  construction: [
    { standard: "OSHA", mandatory: true },
    { standard: "ISO 45001", mandatory: false },
  ],
  automotive: [
    { standard: "ISO 26262", mandatory: true },
    { standard: "TISAX", mandatory: false },
  ],
  pharmaceutical: [
    { standard: "FDA 21 CFR Part 11", mandatory: true },
    { standard: "GxP", mandatory: true },
  ],
  nonprofit: [
    { standard: "IRS", mandatory: true },
    { standard: "State regulations", mandatory: true },
  ],
  mining: [
    { standard: "MSHA", mandatory: true },
    { standard: "ISO 14001", mandatory: false },
  ],
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
  cybersecurity: [
    { standard: "NIST", mandatory: true },
    { standard: "ISO 27001", mandatory: true },
    { standard: "CMMC", mandatory: false },
  ],
  ecommerce: [
    { standard: "PCI-DSS", mandatory: true },
    { standard: "GDPR", mandatory: false },
    { standard: "CCPA", mandatory: false },
  ],
};
