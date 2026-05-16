// ─── Zenic-Agents MCP Gateway — Audit Merkle Chain Type System ──────────
// Immutable audit trail with SHA-256 chain hashing

/** Audit entry for the Merkle chain */
export interface AuditEntry {
  id: string;
  timestamp: number;
  action: string;
  resource: string;
  resourceId?: string;
  actorId?: string;
  actorType: "user" | "system" | "service" | "agent";
  outcome: "success" | "failure" | "denied" | "error";
  severity: "debug" | "info" | "warn" | "error" | "critical";
  details: Record<string, unknown>;
  /** Hash of this entry (SHA-256) */
  hash: string;
  /** Hash of previous entry (Merkle chain) */
  previousHash: string;
  /** Tags for filtering */
  tags: string[];
  /** Trace ID for correlation */
  traceId?: string;
  /** Tenant ID */
  tenantId?: string;
  /** Duration of the operation in ms */
  duration?: number;
}

/** Merkle chain verification result */
export interface MerkleVerificationResult {
  valid: boolean;
  brokenAt?: number; // index where chain is broken
  expectedHash?: string;
  actualHash?: string;
  totalEntries: number;
}

/** Audit query parameters */
export interface AuditQueryParams {
  actorId?: string;
  action?: string;
  resource?: string;
  severity?: string;
  outcome?: string;
  traceId?: string;
  tenantId?: string;
  startDate?: number;
  endDate?: number;
  page?: number;
  pageSize?: number;
}
