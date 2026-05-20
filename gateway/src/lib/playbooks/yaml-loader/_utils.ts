// ─── Zenic-Agents v3 — YAML Loader Utilities ──────────────────────────
// Split from yaml-loader.ts — pure utility functions (hashing, sorting)

/** Recursively sort object keys for deterministic serialization */
export function deepSortKeys(obj: unknown): unknown {
  if (obj === null || obj === undefined) return obj;
  if (Array.isArray(obj)) return obj.map(deepSortKeys);
  if (typeof obj === "object") {
    const sorted: Record<string, unknown> = {};
    for (const key of Object.keys(obj as Record<string, unknown>).sort()) {
      sorted[key] = deepSortKeys((obj as Record<string, unknown>)[key]);
    }
    return sorted;
  }
  return obj;
}
