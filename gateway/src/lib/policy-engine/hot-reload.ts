// ─── Zenic-Agents v3 — Policy Hot-Reload ──────────────────────────────
// Watches for policy changes and reloads them without server restart.
// Uses file system watching or DB polling.
//
// Pattern: Observer — listeners are notified on policy changes

import { db } from "@/lib/db";
import { loadPolicyFromYaml, computeContentHash } from "./yaml-loader";
import { getPolicyEvaluator } from "./evaluator";
import type {
  HotReloadEvent,
  HotReloadEventType,
  HotReloadListener,
  PolicyDocument,
} from "./types";

// ─── Hot-Reload Manager ───────────────────────────────────────────────

export class PolicyHotReloader {
  private listeners: Map<string, Set<HotReloadListener>> = new Map();
  private contentHashCache: Map<string, string> = new Map();
  private pollInterval: ReturnType<typeof setInterval> | null = null;
  private running = false;

  constructor(
    private readonly pollIntervalMs: number = 30_000,
  ) {}

  /**
   * Start watching for policy changes.
   */
  start(): void {
    if (this.running) return;
    this.running = true;

    // Initial snapshot
    this.snapshotHashes().catch((err) => {
      console.error("[PolicyHotReload] Initial snapshot failed:", err);
    });

    // Start polling
    this.pollInterval = setInterval(() => {
      this.checkForChanges().catch((err) => {
        console.error("[PolicyHotReload] Check failed:", err);
      });
    }, this.pollIntervalMs);

    console.log(`[PolicyHotReload] Started (interval: ${this.pollIntervalMs}ms)`);
  }

  /**
   * Stop watching.
   */
  stop(): void {
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
    this.running = false;
    console.log("[PolicyHotReload] Stopped");
  }

  /**
   * Register a listener for hot-reload events.
   */
  addListener(eventType: HotReloadEventType, listener: HotReloadListener): () => void {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, new Set());
    }
    this.listeners.get(eventType)!.add(listener);

    // Return unsubscribe function
    return () => {
      this.listeners.get(eventType)?.delete(listener);
    };
  }

  /**
   * Manually trigger a reload of all policies.
   */
  async reloadAll(): Promise<{ reloaded: number; errors: number }> {
    let reloaded = 0;
    let errors = 0;

    try {
      const policies = await db.declPolicy.findMany({ where: { isActive: true } });

      for (const policy of policies) {
        try {
          // Clear cache entry
          this.contentHashCache.delete(policy.policyId);
          reloaded++;
        } catch {
          errors++;
        }
      }

      // Clear evaluator cache
      getPolicyEvaluator().clearCache();

      // Notify listeners
      this.emit({
        type: "policy_reloaded",
        policyId: "__all__",
        timestamp: new Date().toISOString(),
        description: `Reloaded ${reloaded} policies`,
      });
    } catch (err) {
      console.error("[PolicyHotReload] Reload all failed:", err);
      errors++;
    }

    return { reloaded, errors };
  }

  /**
   * Manually reload a specific policy from YAML.
   */
  async reloadFromYaml(policyId: string, yamlContent: string): Promise<PolicyDocument> {
    const document = loadPolicyFromYaml(yamlContent);
    const contentHash = computeContentHash(document);

    // Update or create in DB
    const existing = await db.declPolicy.findUnique({ where: { policyId } });

    if (existing) {
      const previousHash = existing.contentHash;

      await db.declPolicy.update({
        where: { policyId },
        data: {
          name: document.metadata.name,
          description: document.metadata.description,
          version: document.metadata.version,
          labels: JSON.stringify(document.metadata.labels ?? {}),
          compliance: JSON.stringify(document.metadata.compliance ?? []),
          statements: JSON.stringify(document.statements),
          tests: JSON.stringify(document.tests ?? []),
          sourceYaml: yamlContent,
          contentHash,
          updatedAt: new Date(),
        },
      });

      if (previousHash !== contentHash) {
        this.emit({
          type: "policy_updated",
          policyId,
          version: document.metadata.version,
          timestamp: new Date().toISOString(),
          description: `Policy "${policyId}" updated (hash changed)`,
        });
      }
    } else {
      await db.declPolicy.create({
        data: {
          policyId,
          name: document.metadata.name,
          description: document.metadata.description,
          version: document.metadata.version,
          labels: JSON.stringify(document.metadata.labels ?? {}),
          compliance: JSON.stringify(document.metadata.compliance ?? []),
          statements: JSON.stringify(document.statements),
          tests: JSON.stringify(document.tests ?? []),
          sourceYaml: yamlContent,
          contentHash,
          author: document.metadata.author,
        },
      });

      this.emit({
        type: "policy_added",
        policyId,
        version: document.metadata.version,
        timestamp: new Date().toISOString(),
        description: `Policy "${policyId}" added`,
      });
    }

    // Clear evaluator cache
    getPolicyEvaluator().clearCache();

    return document;
  }

  // ─── Internal ───────────────────────────────────────────────────────

  private async snapshotHashes(): Promise<void> {
    const policies = await db.declPolicy.findMany({
      select: { policyId: true, contentHash: true },
    });

    for (const p of policies) {
      this.contentHashCache.set(p.policyId, p.contentHash);
    }
  }

  private async checkForChanges(): Promise<void> {
    const policies = await db.declPolicy.findMany({
      select: { policyId: true, contentHash: true, version: true },
    });

    // BUG #9 FIX: Build a Map for O(1) lookups instead of O(N) Array.find
    const policyMap = new Map(policies.map((p) => [p.policyId, p]));
    const currentIds = new Set(policyMap.keys());
    const cachedIds = new Set(this.contentHashCache.keys());

    // New policies
    for (const id of currentIds) {
      if (!cachedIds.has(id)) {
        const policy = policyMap.get(id)!;
        this.emit({
          type: "policy_added",
          policyId: id,
          version: policy.version,
          timestamp: new Date().toISOString(),
          description: `New policy "${id}" detected`,
        });
        this.contentHashCache.set(id, policy.contentHash);
        getPolicyEvaluator().clearCache();
      }
    }

    // Removed policies
    for (const id of cachedIds) {
      if (!currentIds.has(id)) {
        this.emit({
          type: "policy_removed",
          policyId: id,
          timestamp: new Date().toISOString(),
          description: `Policy "${id}" removed`,
        });
        this.contentHashCache.delete(id);
        getPolicyEvaluator().clearCache();
      }
    }

    // Updated policies
    for (const policy of policies) {
      const cached = this.contentHashCache.get(policy.policyId);
      if (cached && cached !== policy.contentHash) {
        this.emit({
          type: "policy_updated",
          policyId: policy.policyId,
          version: policy.version,
          timestamp: new Date().toISOString(),
          description: `Policy "${policy.policyId}" updated (hash changed)`,
        });
        this.contentHashCache.set(policy.policyId, policy.contentHash);
        getPolicyEvaluator().clearCache();
      }
    }
  }

  private emit(event: HotReloadEvent): void {
    const listeners = this.listeners.get(event.type);
    if (listeners) {
      for (const listener of listeners) {
        try {
          listener(event);
        } catch (err) {
          console.error(`[PolicyHotReload] Listener error for ${event.type}:`, err);
        }
      }
    }

    // Also notify wildcard listeners
    const allListeners = this.listeners.get("*" as HotReloadEventType);
    if (allListeners) {
      for (const listener of allListeners) {
        try {
          listener(event);
        } catch (err) {
          console.error(`[PolicyHotReload] Wildcard listener error:`, err);
        }
      }
    }
  }
}

// ─── Singleton ────────────────────────────────────────────────────────

let hotReloaderInstance: PolicyHotReloader | null = null;

export function getPolicyHotReloader(intervalMs?: number): PolicyHotReloader {
  if (!hotReloaderInstance) {
    hotReloaderInstance = new PolicyHotReloader(intervalMs);
  }
  return hotReloaderInstance;
}

export function resetPolicyHotReloader(): void {
  if (hotReloaderInstance) {
    hotReloaderInstance.stop();
    hotReloaderInstance = null;
  }
}
