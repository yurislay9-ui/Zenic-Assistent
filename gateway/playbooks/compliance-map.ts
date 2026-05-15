// ─── Zenic-Agents v3 — Playbook Compliance Mapper ──────────────────────
// Phase 4: Visitor pattern — maps playbooks to compliance requirements per industry.
//
// Loads playbooks from DB, maps industry to required compliance standards,
// checks which policies address which standards, calculates coverage, and
// identifies gaps.
//
// Design Patterns:
//   - Visitor: traverses playbook structure (capabilities + policies) to
//     build compliance report, separating data from processing logic
//   - Strategy: industry-specific compliance requirement sets

import type {
  Industry,
  PlaybookCapability,
  PolicyReference,
} from "./types";
import { db } from "@/lib/db";

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

// ─── Compliance Standards Definition ───────────────────────────────────

interface ComplianceStandardDef {
  name: string;
  sections: Record<string, {
    description: string;
    keywords: string[];
    capabilityKeywords: string[];
  }>;
}

/**
 * Comprehensive compliance standards registry.
 * Each standard has sections with keyword patterns for matching against
 * playbook policies and capabilities (visitor traversal).
 */
const COMPLIANCE_STANDARDS: ComplianceStandardDef[] = [
  {
    name: "HIPAA",
    sections: {
      "164.312(a)": { description: "Access control", keywords: ["access", "control", "role", "authorization"], capabilityKeywords: ["access", "rbac", "auth"] },
      "164.312(b)": { description: "Audit controls", keywords: ["audit", "log", "record", "trail"], capabilityKeywords: ["audit", "logging", "monitor"] },
      "164.312(c)": { description: "Integrity controls", keywords: ["integrity", "protect", "modify", "tamper"], capabilityKeywords: ["integrity", "validation"] },
      "164.312(d)": { description: "Person authentication", keywords: ["auth", "identity", "verify", "mfa"], capabilityKeywords: ["auth", "identity", "mfa"] },
      "164.312(e)": { description: "Transmission security", keywords: ["encrypt", "transmit", "secure", "tls"], capabilityKeywords: ["encrypt", "security", "network"] },
      "164.524": { description: "Access of PHI", keywords: ["phi", "access", "patient", "health"], capabilityKeywords: ["health", "patient", "data"] },
      "164.530(j)": { description: "Retain documentation", keywords: ["retain", "document", "record", "archive"], capabilityKeywords: ["report", "document", "archive"] },
    },
  },
  {
    name: "COPPA",
    sections: {
      "312.3": { description: "Parental notice", keywords: ["parent", "notice", "child", "consent"], capabilityKeywords: ["consent", "notification"] },
      "312.4": { description: "Parental consent", keywords: ["parental", "consent", "verifiable"], capabilityKeywords: ["consent", "verification"] },
      "312.5": { description: "Data minimization", keywords: ["minimize", "collect", "data", "limit"], capabilityKeywords: ["data", "minimize"] },
      "312.6": { description: "Security of data", keywords: ["security", "protect", "child", "data"], capabilityKeywords: ["security", "encrypt"] },
      "312.7": { description: "Data retention", keywords: ["retain", "delete", "retention", "dispose"], capabilityKeywords: ["retention", "delete"] },
    },
  },
  {
    name: "HITECH",
    sections: {
      "13402": { description: "Breach notification", keywords: ["breach", "notify", "notification", "incident"], capabilityKeywords: ["notification", "alert", "incident"] },
      "13403": { description: "Breach notification to individuals", keywords: ["individual", "notify", "breach"], capabilityKeywords: ["notification", "alert"] },
      "13404": { description: "Breach notification to media", keywords: ["media", "notify", "breach"], capabilityKeywords: ["notification"] },
      "13405": { description: "Business associate contracts", keywords: ["business", "associate", "contract", "baa"], capabilityKeywords: ["contract", "compliance"] },
    },
  },
  {
    name: "PCI-DSS",
    sections: {
      "1.2.3": { description: "Network configuration standards", keywords: ["network", "firewall", "configuration"], capabilityKeywords: ["network", "firewall"] },
      "1.3.1": { description: "Restrict inbound traffic", keywords: ["traffic", "restrict", "inbound"], capabilityKeywords: ["network", "security"] },
      "2.1": { description: "Change default credentials", keywords: ["credential", "password", "default"], capabilityKeywords: ["auth", "credential"] },
      "3.4": { description: "Render PAN unreadable", keywords: ["encrypt", "card", "pan", "data"], capabilityKeywords: ["encrypt", "data"] },
      "6.5": { description: "Address common vulnerabilities", keywords: ["vulnerability", "security", "input"], capabilityKeywords: ["security", "validation"] },
      "7.1": { description: "Limit access to need-to-know", keywords: ["access", "restrict", "role"], capabilityKeywords: ["access", "rbac"] },
      "7.2": { description: "Access control mechanism", keywords: ["rbac", "access", "control"], capabilityKeywords: ["rbac", "access"] },
      "8.1": { description: "Define user identification", keywords: ["user", "identity", "auth"], capabilityKeywords: ["auth", "identity"] },
      "8.3": { description: "Secure authentication", keywords: ["mfa", "authentication", "secure"], capabilityKeywords: ["auth", "mfa"] },
      "10.1": { description: "Implement audit trails", keywords: ["audit", "log", "trail"], capabilityKeywords: ["audit", "logging"] },
      "10.2": { description: "Automated audit trail", keywords: ["audit", "automated", "track"], capabilityKeywords: ["audit", "automated"] },
    },
  },
  {
    name: "SOX",
    sections: {
      "302": { description: "Corporate responsibility for reports", keywords: ["report", "financial", "responsibility"], capabilityKeywords: ["report", "financial"] },
      "404": { description: "Internal control assessment", keywords: ["control", "internal", "assessment"], capabilityKeywords: ["control", "compliance"] },
      "409": { description: "Real-time issuer disclosure", keywords: ["disclosure", "real-time", "report"], capabilityKeywords: ["report", "realtime"] },
    },
  },
  {
    name: "AML/KYC",
    sections: {
      "3.1": { description: "Customer identification", keywords: ["identify", "customer", "verify"], capabilityKeywords: ["identity", "verification"] },
      "3.2": { description: "Customer due diligence", keywords: ["due", "diligence", "risk"], capabilityKeywords: ["risk", "compliance"] },
      "3.3": { description: "Enhanced due diligence", keywords: ["enhanced", "high-risk", "pep"], capabilityKeywords: ["risk", "monitor"] },
      "4.1": { description: "Transaction monitoring", keywords: ["transaction", "monitor", "suspicious"], capabilityKeywords: ["monitor", "transaction"] },
      "4.2": { description: "Suspicious activity reporting", keywords: ["suspicious", "report", "alert"], capabilityKeywords: ["report", "alert"] },
    },
  },
  {
    name: "GLBA",
    sections: {
      "501(a)": { description: "Privacy of consumer financial information", keywords: ["privacy", "financial", "consumer"], capabilityKeywords: ["privacy", "data"] },
      "501(b)": { description: "Security of consumer information", keywords: ["security", "consumer", "protect"], capabilityKeywords: ["security", "encrypt"] },
      "502": { description: "Obligation to respect opt-out", keywords: ["opt-out", "consent", "privacy"], capabilityKeywords: ["consent", "privacy"] },
      "503": { description: "Disclosure of privacy policy", keywords: ["disclosure", "privacy", "policy"], capabilityKeywords: ["compliance", "report"] },
    },
  },
  {
    name: "GDPR",
    sections: {
      "5": { description: "Principles for processing", keywords: ["consent", "purpose", "minimize"], capabilityKeywords: ["consent", "data"] },
      "6": { description: "Lawfulness of processing", keywords: ["lawful", "consent", "legal"], capabilityKeywords: ["consent", "compliance"] },
      "17": { description: "Right to erasure", keywords: ["erase", "delete", "remove"], capabilityKeywords: ["delete", "data"] },
      "25": { description: "Data protection by design", keywords: ["design", "protect", "default"], capabilityKeywords: ["security", "data"] },
      "30": { description: "Records of processing", keywords: ["record", "processing", "log"], capabilityKeywords: ["logging", "audit"] },
      "32": { description: "Security of processing", keywords: ["security", "encrypt", "protect"], capabilityKeywords: ["security", "encrypt"] },
      "35": { description: "Impact assessment", keywords: ["impact", "assessment", "risk"], capabilityKeywords: ["risk", "assessment"] },
    },
  },
  {
    name: "FERPA",
    sections: {
      "99.30": { description: "Consent for disclosure", keywords: ["consent", "disclosure", "education"], capabilityKeywords: ["consent", "data"] },
      "99.31": { description: "Exceptions to consent", keywords: ["exception", "disclosure", "directory"], capabilityKeywords: ["compliance", "data"] },
      "99.33": { description: "Redisclosure of records", keywords: ["redisclosure", "record", "restrict"], capabilityKeywords: ["data", "access"] },
      "99.35": { description: "Records of disclosures", keywords: ["record", "disclosure", "log"], capabilityKeywords: ["audit", "logging"] },
    },
  },
  {
    name: "ABA Model Rules",
    sections: {
      "1.1": { description: "Competence", keywords: ["competence", "skill", "diligence"], capabilityKeywords: ["compliance", "quality"] },
      "1.6": { description: "Confidentiality of information", keywords: ["confidentiality", "privilege", "protect"], capabilityKeywords: ["security", "encrypt", "data"] },
      "5.1": { description: "Supervisory responsibilities", keywords: ["supervision", "oversight", "responsibility"], capabilityKeywords: ["monitor", "audit"] },
      "5.3": { description: "Assistance regarding nonlawyer assistants", keywords: ["nonlawyer", "assistant", "supervision"], capabilityKeywords: ["monitor", "access"] },
    },
  },
  {
    name: "CCPA",
    sections: {
      "1798.100": { description: "Right to know", keywords: ["know", "access", "information"], capabilityKeywords: ["data", "access"] },
      "1798.105": { description: "Right to delete", keywords: ["delete", "remove", "erase"], capabilityKeywords: ["delete", "data"] },
      "1798.110": { description: "Right to disclosure", keywords: ["disclosure", "information", "collect"], capabilityKeywords: ["report", "data"] },
      "1798.120": { description: "Right to opt-out", keywords: ["opt-out", "sell", "share"], capabilityKeywords: ["consent", "privacy"] },
      "1798.150": { description: "Private right of action", keywords: ["action", "breach", "damage"], capabilityKeywords: ["security", "incident"] },
    },
  },
  {
    name: "ISO 27001",
    sections: {
      "A.5": { description: "Information security policies", keywords: ["policy", "security", "information"], capabilityKeywords: ["policy", "security"] },
      "A.6": { description: "Organization of information security", keywords: ["organization", "security", "governance"], capabilityKeywords: ["compliance", "governance"] },
      "A.8": { description: "Asset management", keywords: ["asset", "management", "inventory"], capabilityKeywords: ["asset", "inventory"] },
      "A.9": { description: "Access control", keywords: ["access", "control", "role"], capabilityKeywords: ["access", "rbac"] },
      "A.10": { description: "Cryptography", keywords: ["cryptograph", "encrypt", "key"], capabilityKeywords: ["encrypt", "security"] },
      "A.12": { description: "Operations security", keywords: ["operations", "security", "monitor"], capabilityKeywords: ["monitor", "security"] },
      "A.16": { description: "Information security incident management", keywords: ["incident", "security", "response"], capabilityKeywords: ["incident", "alert"] },
    },
  },
  {
    name: "NIST",
    sections: {
      "ID.AM": { description: "Asset management", keywords: ["asset", "management", "inventory"], capabilityKeywords: ["asset", "inventory"] },
      "ID.RA": { description: "Risk assessment", keywords: ["risk", "assessment", "vulnerability"], capabilityKeywords: ["risk", "assessment"] },
      "PR.AC": { description: "Access control", keywords: ["access", "control", "identity"], capabilityKeywords: ["access", "rbac", "identity"] },
      "PR.DS": { description: "Data security", keywords: ["data", "security", "protect"], capabilityKeywords: ["security", "encrypt", "data"] },
      "DE.CM": { description: "Security continuous monitoring", keywords: ["monitor", "continuous", "detect"], capabilityKeywords: ["monitor", "detect"] },
      "RS.RP": { description: "Response planning", keywords: ["response", "plan", "incident"], capabilityKeywords: ["incident", "response"] },
      "RC.RP": { description: "Recovery planning", keywords: ["recovery", "plan", "restore"], capabilityKeywords: ["recovery", "backup"] },
    },
  },
  {
    name: "FedRAMP",
    sections: {
      "AC": { description: "Access control family", keywords: ["access", "control", "role"], capabilityKeywords: ["access", "rbac"] },
      "AU": { description: "Audit and accountability", keywords: ["audit", "accountability", "log"], capabilityKeywords: ["audit", "logging"] },
      "CM": { description: "Configuration management", keywords: ["configuration", "baseline", "change"], capabilityKeywords: ["configuration", "compliance"] },
      "IA": { description: "Identification and authentication", keywords: ["identification", "authentication", "identity"], capabilityKeywords: ["auth", "identity"] },
      "SC": { description: "System and communications protection", keywords: ["system", "communication", "protect"], capabilityKeywords: ["security", "network"] },
      "SI": { description: "System and information integrity", keywords: ["system", "integrity", "information"], capabilityKeywords: ["integrity", "security"] },
    },
  },
  {
    name: "FISMA",
    sections: {
      "3544(a)(1)": { description: "Information security policies", keywords: ["policy", "security", "information"], capabilityKeywords: ["policy", "security"] },
      "3544(a)(2)": { description: "Risk-based security", keywords: ["risk", "security", "assessment"], capabilityKeywords: ["risk", "assessment"] },
      "3544(a)(3)": { description: "Security awareness training", keywords: ["training", "awareness", "security"], capabilityKeywords: ["training", "compliance"] },
      "3544(b)": { description: "Security program plan", keywords: ["program", "plan", "security"], capabilityKeywords: ["compliance", "planning"] },
    },
  },
  {
    name: "NAIC",
    sections: {
      "Model 668": { description: "Privacy of consumer financial and health information", keywords: ["privacy", "financial", "health"], capabilityKeywords: ["privacy", "data"] },
      "Model 670": { description: "Standards for safeguarding customer information", keywords: ["safeguard", "customer", "security"], capabilityKeywords: ["security", "data"] },
    },
  },
  {
    name: "NERC CIP",
    sections: {
      "CIP-002": { description: "BES Cyber System Categorization", keywords: ["cyber", "categorization", "system"], capabilityKeywords: ["asset", "classification"] },
      "CIP-003": { description: "Security Management Controls", keywords: ["security", "management", "control"], capabilityKeywords: ["security", "compliance"] },
      "CIP-005": { description: "Electronic Security Perimeters", keywords: ["electronic", "perimeter", "security"], capabilityKeywords: ["network", "security"] },
      "CIP-007": { description: "System Security Management", keywords: ["system", "security", "management"], capabilityKeywords: ["security", "monitor"] },
      "CIP-010": { description: "Configuration Change Management", keywords: ["configuration", "change", "management"], capabilityKeywords: ["configuration", "compliance"] },
    },
  },
  {
    name: "ISO 28000",
    sections: {
      "4.2": { description: "Security management policy", keywords: ["policy", "security", "management"], capabilityKeywords: ["policy", "security"] },
      "4.3": { description: "Security risk assessment", keywords: ["risk", "assessment", "security"], capabilityKeywords: ["risk", "assessment"] },
      "4.4": { description: "Security risk treatment", keywords: ["risk", "treatment", "mitigation"], capabilityKeywords: ["risk", "mitigation"] },
      "4.5": { description: "Security management objectives", keywords: ["objective", "target", "security"], capabilityKeywords: ["compliance", "monitor"] },
    },
  },
  {
    name: "C-TPAT",
    sections: {
      "1": { description: "Business partner requirements", keywords: ["partner", "requirement", "business"], capabilityKeywords: ["compliance", "verification"] },
      "2": { description: "Container security", keywords: ["container", "security", "seal"], capabilityKeywords: ["security", "monitor"] },
      "3": { description: "Physical access controls", keywords: ["physical", "access", "control"], capabilityKeywords: ["access", "security"] },
      "4": { description: "Personnel security", keywords: ["personnel", "security", "background"], capabilityKeywords: ["identity", "security"] },
    },
  },
  {
    name: "FDA",
    sections: {
      "21 CFR 11": { description: "Electronic records; electronic signatures", keywords: ["electronic", "record", "signature"], capabilityKeywords: ["audit", "integrity"] },
      "21 CFR 820": { description: "Quality system regulation", keywords: ["quality", "system", "regulation"], capabilityKeywords: ["quality", "compliance"] },
    },
  },
  {
    name: "USDA compliance",
    sections: {
      "7 CFR 205": { description: "National Organic Program", keywords: ["organic", "certification", "compliance"], capabilityKeywords: ["compliance", "certification"] },
      "9 CFR 417": { description: "HACCP systems", keywords: ["haccp", "hazard", "analysis"], capabilityKeywords: ["monitor", "compliance"] },
    },
  },
  {
    name: "FCC regulations",
    sections: {
      "47 CFR 64": { description: "Carrier practices", keywords: ["carrier", "practice", "regulation"], capabilityKeywords: ["compliance", "monitor"] },
      "47 CFR 22": { description: "Public mobile services", keywords: ["mobile", "service", "spectrum"], capabilityKeywords: ["compliance", "monitor"] },
    },
  },
  {
    name: "DMCA",
    sections: {
      "512": { description: "Online copyright infringement liability limitation", keywords: ["copyright", "infringement", "limitation"], capabilityKeywords: ["compliance", "content"] },
      "1201": { description: "Circumvention of copyright protection systems", keywords: ["circumvention", "copyright", "protection"], capabilityKeywords: ["security", "protection"] },
    },
  },
  {
    name: "OSHA",
    sections: {
      "1910.134": { description: "Respiratory protection", keywords: ["respiratory", "protection", "safety"], capabilityKeywords: ["safety", "compliance"] },
      "1910.1200": { description: "Hazard communication", keywords: ["hazard", "communication", "chemical"], capabilityKeywords: ["compliance", "safety"] },
      "1926.502": { description: "Fall protection systems", keywords: ["fall", "protection", "system"], capabilityKeywords: ["safety", "monitor"] },
    },
  },
  {
    name: "ISO 45001",
    sections: {
      "4.1": { description: "Context of the organization", keywords: ["context", "organization", "oh&s"], capabilityKeywords: ["compliance", "governance"] },
      "6.1": { description: "Actions to address risks and opportunities", keywords: ["risk", "opportunity", "action"], capabilityKeywords: ["risk", "assessment"] },
      "8.1": { description: "Operational planning and control", keywords: ["operational", "planning", "control"], capabilityKeywords: ["compliance", "monitor"] },
      "10.2": { description: "Incident investigation", keywords: ["incident", "investigation", "nonconformity"], capabilityKeywords: ["incident", "audit"] },
    },
  },
  {
    name: "ISO 26262",
    sections: {
      "Part 3": { description: "Concept phase", keywords: ["concept", "hazard", "analysis"], capabilityKeywords: ["risk", "assessment"] },
      "Part 4": { description: "Product development at system level", keywords: ["system", "development", "safety"], capabilityKeywords: ["compliance", "quality"] },
      "Part 6": { description: "Product development at software level", keywords: ["software", "development", "safety"], capabilityKeywords: ["quality", "compliance"] },
      "Part 8": { description: "Supporting processes", keywords: ["support", "process", "configuration"], capabilityKeywords: ["configuration", "compliance"] },
    },
  },
  {
    name: "TISAX",
    sections: {
      "ISA.1": { description: "Information security management", keywords: ["information", "security", "management"], capabilityKeywords: ["security", "compliance"] },
      "ISA.2": { description: "Organizational security", keywords: ["organizational", "security", "policy"], capabilityKeywords: ["policy", "security"] },
      "ISA.3": { description: "Personnel security", keywords: ["personnel", "security", "awareness"], capabilityKeywords: ["identity", "security"] },
    },
  },
  {
    name: "FDA 21 CFR Part 11",
    sections: {
      "11.10": { description: "Controls for closed systems", keywords: ["closed", "system", "audit"], capabilityKeywords: ["audit", "compliance"] },
      "11.30": { description: "Controls for open systems", keywords: ["open", "system", "security"], capabilityKeywords: ["security", "encrypt"] },
      "11.50": { description: "Signature manifestations", keywords: ["signature", "manifestation", "electronic"], capabilityKeywords: ["audit", "identity"] },
      "11.70": { description: "Signature/record linking", keywords: ["signature", "link", "record"], capabilityKeywords: ["audit", "integrity"] },
    },
  },
  {
    name: "GxP",
    sections: {
      "GLP": { description: "Good Laboratory Practice", keywords: ["laboratory", "practice", "quality"], capabilityKeywords: ["quality", "compliance"] },
      "GMP": { description: "Good Manufacturing Practice", keywords: ["manufacturing", "practice", "quality"], capabilityKeywords: ["quality", "compliance", "manufacturing"] },
      "GCP": { description: "Good Clinical Practice", keywords: ["clinical", "practice", "trial"], capabilityKeywords: ["compliance", "audit"] },
    },
  },
  {
    name: "IRS",
    sections: {
      "501(c)(3)": { description: "Tax-exempt organizations", keywords: ["tax", "exempt", "organization"], capabilityKeywords: ["compliance", "report"] },
      "990": { description: "Return of organization exempt from income tax", keywords: ["return", "exempt", "income"], capabilityKeywords: ["report", "financial"] },
    },
  },
  {
    name: "State regulations",
    sections: {
      "AG": { description: "Attorney General registration", keywords: ["registration", "attorney", "general"], capabilityKeywords: ["compliance", "report"] },
      "Charity": { description: "Charitable solicitation registration", keywords: ["charity", "solicitation", "registration"], capabilityKeywords: ["compliance", "report"] },
    },
  },
  {
    name: "MSHA",
    sections: {
      "30 CFR 56": { description: "Surface metal and nonmetal mines", keywords: ["surface", "mine", "safety"], capabilityKeywords: ["safety", "compliance"] },
      "30 CFR 57": { description: "Underground metal and nonmetal mines", keywords: ["underground", "mine", "safety"], capabilityKeywords: ["safety", "compliance"] },
      "30 CFR 75": { description: "Mandatory safety standards - underground coal", keywords: ["coal", "underground", "mandatory"], capabilityKeywords: ["compliance", "safety"] },
    },
  },
  {
    name: "ISO 14001",
    sections: {
      "4.1": { description: "Context of the organization", keywords: ["context", "environmental", "organization"], capabilityKeywords: ["compliance", "governance"] },
      "6.1": { description: "Actions to address risks", keywords: ["risk", "environmental", "aspect"], capabilityKeywords: ["risk", "assessment"] },
      "8.1": { description: "Operational planning and control", keywords: ["operational", "planning", "environmental"], capabilityKeywords: ["compliance", "monitor"] },
      "9.1": { description: "Monitoring, measurement, analysis", keywords: ["monitor", "measure", "environmental"], capabilityKeywords: ["monitor", "analytics"] },
    },
  },
  {
    name: "Basel III",
    sections: {
      "Liquidity": { description: "Liquidity coverage ratio", keywords: ["liquidity", "coverage", "ratio"], capabilityKeywords: ["financial", "monitor"] },
      "Capital": { description: "Capital adequacy requirements", keywords: ["capital", "adequacy", "requirement"], capabilityKeywords: ["financial", "compliance"] },
      "Leverage": { description: "Leverage ratio", keywords: ["leverage", "ratio", "exposure"], capabilityKeywords: ["financial", "monitor"] },
    },
  },
  {
    name: "SOC 2",
    sections: {
      "CC6.1": { description: "Logical and physical access controls", keywords: ["access", "control", "logical", "physical"], capabilityKeywords: ["access", "rbac"] },
      "CC6.2": { description: "System account management", keywords: ["account", "management", "provisioning"], capabilityKeywords: ["identity", "access"] },
      "CC7.1": { description: "Detection and monitoring", keywords: ["detect", "monitor", "security"], capabilityKeywords: ["monitor", "detect"] },
      "CC7.2": { description: "Incident response", keywords: ["incident", "response", "security"], capabilityKeywords: ["incident", "response"] },
      "CC8.1": { description: "Change management", keywords: ["change", "management", "control"], capabilityKeywords: ["configuration", "compliance"] },
    },
  },
  {
    name: "CMMC",
    sections: {
      "AC": { description: "Access Control", keywords: ["access", "control", "restrict"], capabilityKeywords: ["access", "rbac"] },
      "AU": { description: "Audit and Accountability", keywords: ["audit", "accountability", "log"], capabilityKeywords: ["audit", "logging"] },
      "CM": { description: "Configuration Management", keywords: ["configuration", "baseline", "change"], capabilityKeywords: ["configuration", "compliance"] },
      "IA": { description: "Identification and Authentication", keywords: ["identification", "authentication"], capabilityKeywords: ["auth", "identity"] },
      "MP": { description: "Media Protection", keywords: ["media", "protection", "sanitize"], capabilityKeywords: ["security", "data"] },
    },
  },
];

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
