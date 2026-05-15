// ─── Zenic-Agents v3 — Policy Diff Engine ─────────────────────────────
// Computes differences between two policy document versions.
// Generates structured diff entries for metadata, statements, and tests.
//
// Pattern: Visitor — traverses policy structure to detect changes

import type {
  PolicyDocument,
  PolicyStatement,
  PolicyCondition,
  PolicyTestCase,
  PolicyDiff,
  DiffEntry,
  DiffSummary,
  DiffChangeType,
} from "./types";

// ─── Main Diff Function ───────────────────────────────────────────────

/**
 * Compute the diff between two policy documents.
 */
export function diffPolicies(
  from: PolicyDocument,
  to: PolicyDocument,
): PolicyDiff {
  const metadataChanges = diffMetadata(from.metadata, to.metadata);
  const statementChanges = diffStatements(from.statements, to.statements);
  const testChanges = diffTests(from.tests ?? [], to.tests ?? []);

  const allChanges = [...metadataChanges, ...statementChanges, ...testChanges];
  const summary = computeSummary(allChanges);

  return {
    fromVersion: from.metadata.version,
    toVersion: to.metadata.version,
    metadataChanges,
    statementChanges,
    testChanges,
    summary,
  };
}

// ─── Metadata Diff ────────────────────────────────────────────────────

function diffMetadata(
  from: PolicyDocument["metadata"],
  to: PolicyDocument["metadata"],
): DiffEntry[] {
  const entries: DiffEntry[] = [];

  // Simple field comparisons
  const fields: Array<{ key: keyof typeof from; label: string }> = [
    { key: "name", label: "Name" },
    { key: "version", label: "Version" },
    { key: "description", label: "Description" },
    { key: "author", label: "Author" },
  ];

  for (const { key, label } of fields) {
    if (from[key] !== to[key]) {
      entries.push({
        changeType: "modified" as DiffChangeType,
        path: `metadata.${key}`,
        oldValue: from[key],
        newValue: to[key],
        description: `${label} changed from "${String(from[key])}" to "${String(to[key])}"`,
      });
    }
  }

  // Labels diff
  if (JSON.stringify(from.labels ?? {}) !== JSON.stringify(to.labels ?? {})) {
    entries.push({
      changeType: "modified" as DiffChangeType,
      path: "metadata.labels",
      oldValue: from.labels,
      newValue: to.labels,
      description: "Labels changed",
    });
  }

  // Compliance diff
  if (JSON.stringify(from.compliance ?? []) !== JSON.stringify(to.compliance ?? [])) {
    entries.push({
      changeType: "modified" as DiffChangeType,
      path: "metadata.compliance",
      oldValue: from.compliance,
      newValue: to.compliance,
      description: "Compliance mappings changed",
    });
  }

  return entries;
}

// ─── Statement Diff ───────────────────────────────────────────────────

function diffStatements(
  from: PolicyStatement[],
  to: PolicyStatement[],
): DiffEntry[] {
  const entries: DiffEntry[] = [];

  const fromMap = new Map(from.map((s) => [s.id, s]));
  const toMap = new Map(to.map((s) => [s.id, s]));

  // Find added statements
  for (const [id, statement] of toMap) {
    if (!fromMap.has(id)) {
      entries.push({
        changeType: "added" as DiffChangeType,
        path: `statements[${id}]`,
        newValue: statement,
        description: `Statement "${id}" added (effect: ${statement.effect}, resource: ${statement.resource})`,
      });
    }
  }

  // Find removed statements
  for (const [id, statement] of fromMap) {
    if (!toMap.has(id)) {
      entries.push({
        changeType: "removed" as DiffChangeType,
        path: `statements[${id}]`,
        oldValue: statement,
        description: `Statement "${id}" removed (was: ${statement.effect} on ${statement.resource})`,
      });
    }
  }

  // Find modified statements
  for (const [id, fromStmt] of fromMap) {
    const toStmt = toMap.get(id);
    if (!toStmt) continue;

    const fieldDiffs = diffStatementFields(id, fromStmt, toStmt);
    entries.push(...fieldDiffs);
  }

  return entries;
}

function diffStatementFields(
  id: string,
  from: PolicyStatement,
  to: PolicyStatement,
): DiffEntry[] {
  const entries: DiffEntry[] = [];
  const prefix = `statements[${id}]`;

  // Simple field comparisons
  const fields: Array<{ key: keyof PolicyStatement; label: string }> = [
    { key: "effect", label: "Effect" },
    { key: "resource", label: "Resource" },
    { key: "action", label: "Action" },
    { key: "priority", label: "Priority" },
    { key: "description", label: "Description" },
    { key: "requiredRole", label: "Required Role" },
  ];

  for (const { key, label } of fields) {
    if (from[key] !== to[key]) {
      entries.push({
        changeType: "modified" as DiffChangeType,
        path: `${prefix}.${key}`,
        oldValue: from[key],
        newValue: to[key],
        description: `${label} changed from "${String(from[key])}" to "${String(to[key])}"`,
      });
    }
  }

  // Tags diff
  if (JSON.stringify(from.tags ?? []) !== JSON.stringify(to.tags ?? [])) {
    entries.push({
      changeType: "modified" as DiffChangeType,
      path: `${prefix}.tags`,
      oldValue: from.tags,
      newValue: to.tags,
      description: `Tags changed`,
    });
  }

  // Conditions diff
  const fromConds = from.conditions ?? [];
  const toConds = to.conditions ?? [];
  if (JSON.stringify(fromConds) !== JSON.stringify(toConds)) {
    entries.push({
      changeType: "modified" as DiffChangeType,
      path: `${prefix}.conditions`,
      oldValue: fromConds,
      newValue: toConds,
      description: `Conditions changed (${fromConds.length} → ${toConds.length})`,
    });
  }

  return entries;
}

// ─── Test Diff ────────────────────────────────────────────────────────

function diffTests(
  from: PolicyTestCase[],
  to: PolicyTestCase[],
): DiffEntry[] {
  const entries: DiffEntry[] = [];

  const fromMap = new Map(from.map((t) => [t.name, t]));
  const toMap = new Map(to.map((t) => [t.name, t]));

  // Added tests
  for (const [name, test] of toMap) {
    if (!fromMap.has(name)) {
      entries.push({
        changeType: "added" as DiffChangeType,
        path: `tests[${name}]`,
        newValue: test,
        description: `Test "${name}" added`,
      });
    }
  }

  // Removed tests
  for (const [name, test] of fromMap) {
    if (!toMap.has(name)) {
      entries.push({
        changeType: "removed" as DiffChangeType,
        path: `tests[${name}]`,
        oldValue: test,
        description: `Test "${name}" removed`,
      });
    }
  }

  // Modified tests
  for (const [name, fromTest] of fromMap) {
    const toTest = toMap.get(name);
    if (!toTest) continue;

    if (JSON.stringify(fromTest) !== JSON.stringify(toTest)) {
      entries.push({
        changeType: "modified" as DiffChangeType,
        path: `tests[${name}]`,
        oldValue: fromTest,
        newValue: toTest,
        description: `Test "${name}" modified`,
      });
    }
  }

  return entries;
}

// ─── Summary ──────────────────────────────────────────────────────────

function computeSummary(entries: DiffEntry[]): DiffSummary {
  return {
    added: entries.filter((e) => e.changeType === "added").length,
    removed: entries.filter((e) => e.changeType === "removed").length,
    modified: entries.filter((e) => e.changeType === "modified").length,
    unchanged: 0, // We don't track unchanged entries explicitly
  };
}

/**
 * Generate a human-readable diff summary string.
 */
export function formatDiffSummary(diff: PolicyDiff): string {
  const { summary } = diff;
  const parts: string[] = [];

  if (summary.added > 0) parts.push(`+${summary.added} added`);
  if (summary.removed > 0) parts.push(`-${summary.removed} removed`);
  if (summary.modified > 0) parts.push(`~${summary.modified} modified`);

  if (parts.length === 0) return `No changes between v${diff.fromVersion} → v${diff.toVersion}`;

  return `v${diff.fromVersion} → v${diff.toVersion}: ${parts.join(", ")}`;
}
