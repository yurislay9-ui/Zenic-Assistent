// ─── Zenic-Agents v3 — Onboarding System Types ────────────────────────
// Split from types.ts — onboarding steps, sessions, and configuration

import type { OnboardingStepType, OnboardingSessionStatus } from "./_enums";

/** A single onboarding step — guides the user through playbook setup */
export interface OnboardingStep {
  /** Unique step identifier (e.g., "select-region", "configure-approval-threshold") */
  id: string;
  /** Step title shown to the user */
  title: string;
  /** Detailed description of what this step configures */
  description: string;
  /** Step type — determines UI rendering and validation */
  type: OnboardingStepType;
  /** Field name in the resulting configuration object */
  field: string;
  /** Available options for selection steps */
  options?: Array<{
    /** Option value */
    value: string;
    /** Human-readable label */
    label: string;
    /** Whether this is the default selection */
    default?: boolean;
  }>;
  /** Default value if the user skips this step */
  default_value: unknown;
  /** Whether this step must be completed (cannot be skipped) */
  required: boolean;
}

/** Onboarding configuration embedded in the playbook document */
export interface PlaybookOnboardingConfig {
  /** Ordered list of onboarding steps */
  steps: OnboardingStep[];
  /** Estimated time to complete all steps (minutes) */
  estimated_minutes: number;
}

/** An active onboarding session for a tenant */
export interface OnboardingSession {
  /** Playbook ID being onboarded */
  playbookId: string;
  /** Unique session identifier */
  sessionId: string;
  /** Current session status */
  status: OnboardingSessionStatus;
  /** User answers keyed by step field name */
  answers: Record<string, unknown>;
  /** Snapshot of the generated configuration after completion */
  config_snapshot?: Record<string, unknown>;
  /** Session creation timestamp (ISO 8601) */
  created: string;
  /** Last update timestamp (ISO 8601) */
  updated: string;
}
