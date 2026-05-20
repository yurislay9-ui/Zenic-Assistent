// ─── Policy Diff ──────────────────────────────────────────────────────

/** A diff between two policy versions */
export interface PolicyDiff {
  /** Source version */
  fromVersion: string;
  /** Target version */
  toVersion: string;
  /** Metadata changes */
  metadataChanges: DiffEntry[];
  /** Statement changes */
  statementChanges: DiffEntry[];
  /** Test changes */
  testChanges: DiffEntry[];
  /** Summary stats */
  summary: DiffSummary;
}

/** A single diff entry */
export interface DiffEntry {
  /** Change type */
  changeType: DiffChangeType;
  /** Path within the document (e.g., "statements[2].conditions[0]") */
  path: string;
  /** Old value (for modified/removed) */
  oldValue?: unknown;
  /** New value (for modified/added) */
  newValue?: unknown;
  /** Human-readable description */
  description: string;
}

/** Diff summary statistics */
export interface DiffSummary {
  added: number;
  removed: number;
  modified: number;
  unchanged: number;
}

