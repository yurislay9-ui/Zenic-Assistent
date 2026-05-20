// ─── Zenic-Agents v3 — Certification Module Barrel Export ────────────
// Public API for the certification module.
// Import path `./certification` resolves here via TS directory/index.ts convention.

export type { CertificationVerification, CertificationStatusInfo } from "./types";

export {
  requestCertification,
  verifyCertification,
  revokeCertification,
} from "./_certifier";

export {
  generatePlaybookFingerprint,
  getCertificationStatus,
} from "./_workflow";
