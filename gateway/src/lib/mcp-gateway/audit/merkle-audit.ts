// ─── Zenic-Agents MCP Gateway — Merkle Audit Service ───────────────────
// Immutable audit trail using SHA-256 Merkle chain hashing.
// Each entry's hash includes the previous entry's hash, creating a
// tamper-evident chain. Any modification to a past entry invalidates
// all subsequent hashes, making the audit trail cryptographically verifiable.

import { createHash } from "crypto";
import { AuditEntry, MerkleVerificationResult, AuditQueryParams } from "./types";

/** Maximum entries in the in-memory chain before flush is required (INVARIANT 3) */
const MAX_CHAIN_SIZE = 500;

export class MerkleAuditService {
  private chain: AuditEntry[] = [];
  private genesisHash = "0000000000000000000000000000000000000000000000000000000000000000";
  private _flushCallback: ((entries: AuditEntry[]) => Promise<void>) | null = null;

  /** Set a callback to persist entries when the chain reaches MAX_CHAIN_SIZE.
   *  The callback receives the entries to persist and should clear them
   *  from its own storage after successful persistence.
   *  FIX #9: Permite flush periódico para evitar crecimiento infinito en memoria.
   */
  onFlush(callback: (entries: AuditEntry[]) => Promise<void>): void {
    this._flushCallback = callback;
  }

  /** Record an audit entry in the Merkle chain */
  record(params: Omit<AuditEntry, "id" | "hash" | "previousHash" | "timestamp">): AuditEntry {
    const previousHash = this.chain.length > 0 ? this.chain[this.chain.length - 1].hash : this.genesisHash;

    // Build the entry without hash first, then compute and assign
    const entry: AuditEntry = {
      id: this.generateId(),
      timestamp: Date.now(),
      previousHash,
      ...params,
      hash: "", // placeholder — computed below
    };

    // Compute hash of this entry (including previousHash for chain integrity)
    entry.hash = this.computeHash(entry);

    this.chain.push(entry);

    // FIX #9: Si la cadena excede MAX_CHAIN_SIZE, ejecutar flush callback
    if (this.chain.length >= MAX_CHAIN_SIZE && this._flushCallback) {
      // Flush sin bloquear el return — fire-and-forget con manejo de errores
      const entriesToFlush = [...this.chain];
      this.chain = []; // Reset — la cadena empieza de nuevo con el último hash como genesis
      this._flushCallback(entriesToFlush).catch((err) => {
        console.error("[MerkleAudit] Flush callback failed:", err);
        // Re-insertar las entradas fallidas al inicio de la cadena
        this.chain = [...entriesToFlush, ...this.chain];
      });
    }

    return entry;
  }

  /** Record multiple entries atomically */
  recordBatch(entries: Array<Omit<AuditEntry, "id" | "hash" | "previousHash" | "timestamp">>): AuditEntry[] {
    const results: AuditEntry[] = [];
    for (const entry of entries) {
      results.push(this.record(entry));
    }
    return results;
  }

  /** Verify the entire Merkle chain integrity */
  verify(): MerkleVerificationResult {
    if (this.chain.length === 0) {
      return { valid: true, totalEntries: 0 };
    }

    // Verify genesis link
    if (this.chain[0].previousHash !== this.genesisHash) {
      return {
        valid: false,
        brokenAt: 0,
        expectedHash: this.genesisHash,
        actualHash: this.chain[0].previousHash,
        totalEntries: this.chain.length,
      };
    }

    // Verify each link
    for (let i = 0; i < this.chain.length; i++) {
      const entry = this.chain[i];
      const expectedHash = this.computeHash(entry);

      if (entry.hash !== expectedHash) {
        return {
          valid: false,
          brokenAt: i,
          expectedHash,
          actualHash: entry.hash,
          totalEntries: this.chain.length,
        };
      }

      if (i > 0 && entry.previousHash !== this.chain[i - 1].hash) {
        return {
          valid: false,
          brokenAt: i,
          expectedHash: this.chain[i - 1].hash,
          actualHash: entry.previousHash,
          totalEntries: this.chain.length,
        };
      }
    }

    return { valid: true, totalEntries: this.chain.length };
  }

  /** Query audit entries with filters */
  query(params: AuditQueryParams): { entries: AuditEntry[]; total: number; page: number; pageSize: number } {
    let filtered = [...this.chain];

    if (params.actorId) filtered = filtered.filter((e) => e.actorId === params.actorId);
    if (params.action) filtered = filtered.filter((e) => e.action === params.action);
    if (params.resource) filtered = filtered.filter((e) => e.resource === params.resource);
    if (params.severity) filtered = filtered.filter((e) => e.severity === params.severity);
    if (params.outcome) filtered = filtered.filter((e) => e.outcome === params.outcome);
    if (params.traceId) filtered = filtered.filter((e) => e.traceId === params.traceId);
    if (params.tenantId) filtered = filtered.filter((e) => e.tenantId === params.tenantId);
    if (params.startDate) filtered = filtered.filter((e) => e.timestamp >= params.startDate!);
    if (params.endDate) filtered = filtered.filter((e) => e.timestamp <= params.endDate!);

    // Sort newest first
    filtered.sort((a, b) => b.timestamp - a.timestamp);

    const page = params.page ?? 1;
    const pageSize = params.pageSize ?? 20;
    const start = (page - 1) * pageSize;
    const entries = filtered.slice(start, start + pageSize);

    return { entries, total: filtered.length, page, pageSize };
  }

  /** Get the latest hash (for verification endpoints) */
  getLatestHash(): string {
    return this.chain.length > 0 ? this.chain[this.chain.length - 1].hash : this.genesisHash;
  }

  /** Get chain length */
  get length(): number {
    return this.chain.length;
  }

  /** Compute SHA-256 hash of an audit entry */
  private computeHash(entry: AuditEntry): string {
    const data = JSON.stringify({
      id: entry.id,
      timestamp: entry.timestamp,
      action: entry.action,
      resource: entry.resource,
      resourceId: entry.resourceId,
      actorId: entry.actorId,
      actorType: entry.actorType,
      outcome: entry.outcome,
      severity: entry.severity,
      previousHash: entry.previousHash,
      // Exclude 'hash' itself to prevent circular hashing
    });
    return createHash("sha256").update(data).digest("hex");
  }

  /** Generate unique ID */
  private generateId(): string {
    const timestamp = Date.now().toString(36);
    const random = Math.random().toString(36).slice(2, 8);
    return `aud_${timestamp}_${random}`;
  }
}
