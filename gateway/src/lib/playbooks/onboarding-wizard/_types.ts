// ─── Onboarding Wizard Types ───────────────────────────────────────────
// Result types for onboarding operations. Extracted from onboarding-wizard.ts.

import type {
  OnboardingStep,
  OnboardingStepType,
  OnboardingSessionStatus,
} from "../types";

/** Result of processing a single onboarding step */
export interface OnboardingStepResult {
  /** Whether the step was processed successfully */
  success: boolean;
  /** The session ID */
  sessionId: string;
  /** The step ID that was processed */
  stepId: string;
  /** Whether the answer was valid */
  valid: boolean;
  /** Validation error message if the answer was invalid */
  validationError?: string;
  /** The next step to present (undefined if completed or no more steps) */
  nextStep?: OnboardingStep;
  /** Current progress information */
  progress: OnboardingProgress;
  /** Updated session status */
  sessionStatus: OnboardingSessionStatus;
}

/** Result of completing the onboarding process */
export interface OnboardingCompletionResult {
  /** Whether the onboarding was completed successfully */
  success: boolean;
  /** The session ID */
  sessionId: string;
  /** The generated configuration snapshot */
  configSnapshot: Record<string, unknown>;
  /** Any warnings generated during completion */
  warnings: string[];
  /** Error message if completion failed */
  error?: string;
}

/** Progress information for an onboarding session */
export interface OnboardingProgress {
  /** Total number of steps */
  totalSteps: number;
  /** Number of completed steps */
  completedSteps: number;
  /** Completion percentage (0-100) */
  percentage: number;
  /** Remaining step IDs */
  remainingStepIds: string[];
  /** Remaining step titles */
  remainingStepTitles: string[];
}
