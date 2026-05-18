// ─── Hot-Reload ───────────────────────────────────────────────────────

/** A hot-reload event */
export interface HotReloadEvent {
  /** Event type */
  type: HotReloadEventType;
  /** Affected policy ID */
  policyId: string;
  /** Policy version affected */
  version?: string;
  /** Timestamp */
  timestamp: string;
  /** Description */
  description: string;
}

/** Hot-reload listener callback */
export type HotReloadListener = (event: HotReloadEvent) => void;

// ─── Compliance Mapping ───────────────────────────────────────────────

/** Compliance report for a policy */
export interface ComplianceReport {
  /** Policy ID */
  policyId: string;
  /** Policy version */
  version: string;
  /** Mapped standards */
  standards: Array<{
    /** Standard name */
    name: string;
    /** Mapped sections */
    sections: Array<{
      /** Section reference */
      ref: string;
      /** Controlling statement IDs */
      statementIds: string[];
      /** Coverage confidence (0-1) */
      confidence: number;
    }>;
    /** Overall coverage for this standard (0-1) */
    coverage: number;
  }>;
  /** Overall compliance score (0-100) */
  overallScore: number;
  /** Uncovered requirements */
  gaps: string[];
}

// ─── Policy Engine Configuration ───────────────────────────────────────

/** Policy engine configuration */
export interface PolicyEngineConfig {
  /** Default effect when no policy matches */
  defaultEffect: PolicyEffectV2;
  /** Whether to deny on evaluation error */
  denyOnError: boolean;
  /** Maximum number of policies to evaluate */
  maxPolicies: number;
  /** Whether to cache evaluation results */
  enableCache: boolean;
  /** Cache TTL in seconds */
  cacheTtlSeconds: number;
  /** Whether hot-reload is enabled */
  enableHotReload: boolean;
  /** Hot-reload check interval in seconds */
  hotReloadIntervalSeconds: number;
  /** Policy file directory (for YAML loading) */
  policyDirectory?: string;
}

/** Default engine configuration */
export const DEFAULT_POLICY_ENGINE_CONFIG: PolicyEngineConfig = {
  defaultEffect: PolicyEffectV2.DENY,
  denyOnError: true,
  maxPolicies: 100,
  enableCache: true,
  cacheTtlSeconds: 300,
  enableHotReload: true,
  hotReloadIntervalSeconds: 30,
};

