// ─── Zenic-Agents v3 — Certification Result Types ────────────────────
// Interfaces for certification verification and status information.

import type { CertificationStatus } from "../types";

/** Verification result for a certified playbook */
export interface CertificationVerification {
  /** Whether the certification is valid */
  valid: boolean;
  /** Playbook ID that was verified */
  playbookId: string;
  /** Current certification status */
  status: CertificationStatus;
  /** Whether the content hash matches */
  hashMatches: boolean;
  /** Whether the signature matches */
  signatureMatches: boolean;
  /** Whether the certification has been revoked */
  revoked: boolean;
  /** Human-readable verification details */
  details: string;
  /** When the certification was originally signed (ISO 8601) */
  signedAt?: string;
  /** Who signed the certification */
  signedBy?: string;
}

/** Certification status information for a playbook */
export interface CertificationStatusInfo {
  /** Playbook ID */
  playbookId: string;
  /** Current certification status */
  status: CertificationStatus;
  /** Who signed the certification (if certified) */
  signedBy?: string;
  /** When the certification was signed (ISO 8601) */
  signedAt?: string;
  /** The content hash at the time of certification */
  contentHash?: string;
  /** Whether the current content hash matches the certified hash */
  hashIntact: boolean;
  /** Human-readable status description */
  description: string;
}
