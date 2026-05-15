// ─── Zenic-Agents v3 — Playbook Onboarding Wizard ─────────────────────
// Factory + State Machine pattern for interactive playbook onboarding.
// Manages session lifecycle: create → step → step → ... → complete | abandon
//
// Design Patterns:
//   - Factory: createOnboardingSession builds sessions from playbook definitions
//   - State Machine: session transitions through in_progress → completed | abandoned
//   - Strategy: answer validation varies by OnboardingStepType

import { randomUUID } from "crypto";
import { db } from "@/lib/db";
import type {
  OnboardingSession,
  OnboardingStep,
  OnboardingStepType,
  PlaybookOnboardingConfig,
  OnboardingSessionStatus,
} from "./types";
import {
  OnboardingSessionStatus as OnboardingSessionStatusEnum,
  OnboardingStepType as OnboardingStepTypeEnum,
} from "./types";

// ─── Result Types ─────────────────────────────────────────────────────

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

// ─── Session Creation ────────────────────────────────────────────────

/**
 * Create a new onboarding session for a playbook.
 * Loads the playbook from DB, initializes answers with step defaults,
 * persists the session, and returns it.
 */
export async function createOnboardingSession(
  playbookId: string,
  tenantId?: string,
): Promise<OnboardingSession> {
  try {
    // Load playbook from DB
    const playbook = await db.playbook.findFirst({
      where: { playbookId },
    });

    if (!playbook) {
      throw new Error(`Playbook "${playbookId}" not found`);
    }

    if (!playbook.isActive) {
      throw new Error(`Playbook "${playbookId}" is not active`);
    }

    // Parse onboarding config
    const onboardingConfig: PlaybookOnboardingConfig = JSON.parse(playbook.onboarding);

    if (!onboardingConfig.steps || onboardingConfig.steps.length === 0) {
      throw new Error(`Playbook "${playbookId}" has no onboarding steps defined`);
    }

    // Generate session ID
    const sessionId = `onb_${Date.now().toString(36)}_${randomUUID().slice(0, 8)}`;

    // Initialize answers with defaults from step definitions
    const answers: Record<string, unknown> = {};
    for (const step of onboardingConfig.steps) {
      if (step.default_value !== undefined && step.default_value !== null) {
        answers[step.field] = step.default_value;
      }
    }

    const now = new Date().toISOString();

    // Persist to DB
    await db.playbookOnboardingSession.create({
      data: {
        playbookDbId: playbook.id,
        tenantId: tenantId ?? null,
        sessionId,
        status: OnboardingSessionStatusEnum.IN_PROGRESS,
        currentStep: 0,
        answers: JSON.stringify(answers),
        configSnapshot: "{}",
      },
    });

    return {
      playbookId,
      sessionId,
      status: OnboardingSessionStatusEnum.IN_PROGRESS,
      answers,
      config_snapshot: undefined,
      created: now,
      updated: now,
    };
  } catch (error) {
    throw new Error(
      `Failed to create onboarding session: ${error instanceof Error ? error.message : String(error)}`,
    );
  }
}

// ─── Session Retrieval ───────────────────────────────────────────────

/**
 * Load an onboarding session from DB by session ID.
 */
export async function getOnboardingSession(
  sessionId: string,
): Promise<OnboardingSession | null> {
  try {
    const session = await db.playbookOnboardingSession.findFirst({
      where: { sessionId },
      include: { playbook: { select: { playbookId: true } } },
    });

    if (!session) return null;

    return {
      playbookId: session.playbook.playbookId,
      sessionId: session.sessionId,
      status: session.status as OnboardingSessionStatus,
      answers: JSON.parse(session.answers),
      config_snapshot: session.configSnapshot && session.configSnapshot !== "{}"
        ? JSON.parse(session.configSnapshot)
        : undefined,
      created: session.createdAt.toISOString(),
      updated: session.updatedAt.toISOString(),
    };
  } catch (error) {
    throw new Error(
      `Failed to get onboarding session: ${error instanceof Error ? error.message : String(error)}`,
    );
  }
}

// ─── Step Processing ─────────────────────────────────────────────────

/**
 * Process an answer for a specific onboarding step.
 * Validates the answer, updates the session, advances the current step,
 * and returns the step result with next step info.
 */
export async function processOnboardingStep(
  sessionId: string,
  stepId: string,
  answer: unknown,
): Promise<OnboardingStepResult> {
  try {
    // Load session with playbook
    const session = await db.playbookOnboardingSession.findFirst({
      where: { sessionId },
      include: { playbook: true },
    });

    if (!session) {
      return {
        success: false,
        sessionId,
        stepId,
        valid: false,
        validationError: `Session "${sessionId}" not found`,
        progress: { totalSteps: 0, completedSteps: 0, percentage: 0, remainingStepIds: [], remainingStepTitles: [] },
        sessionStatus: OnboardingSessionStatusEnum.ABANDONED,
      };
    }

    if (session.status !== OnboardingSessionStatusEnum.IN_PROGRESS) {
      return {
        success: false,
        sessionId,
        stepId,
        valid: false,
        validationError: `Session is ${session.status}, cannot process steps`,
        progress: computeProgress(0, []),
        sessionStatus: session.status as OnboardingSessionStatus,
      };
    }

    // Parse onboarding config and answers
    const onboardingConfig: PlaybookOnboardingConfig = JSON.parse(session.playbook.onboarding);
    const answers: Record<string, unknown> = JSON.parse(session.answers);

    // Find the step being answered
    const stepIndex = onboardingConfig.steps.findIndex((s) => s.id === stepId);

    if (stepIndex === -1) {
      return {
        success: false,
        sessionId,
        stepId,
        valid: false,
        validationError: `Step "${stepId}" not found in playbook onboarding`,
        progress: computeProgress(session.currentStep, onboardingConfig.steps),
        sessionStatus: OnboardingSessionStatusEnum.IN_PROGRESS,
      };
    }

    const step = onboardingConfig.steps[stepIndex];

    // Validate answer against step definition
    const validation = validateStepAnswer(step, answer);

    if (!validation.valid) {
      return {
        success: false,
        sessionId,
        stepId,
        valid: false,
        validationError: validation.error,
        progress: computeProgress(session.currentStep, onboardingConfig.steps),
        sessionStatus: OnboardingSessionStatusEnum.IN_PROGRESS,
      };
    }

    // Update answers
    answers[step.field] = answer;

    // Advance current step
    const newCurrentStep = Math.min(stepIndex + 1, onboardingConfig.steps.length);
    const isLastStep = newCurrentStep >= onboardingConfig.steps.length;

    // Check if this is the last step → mark completed, generate config_snapshot
    if (isLastStep) {
      const configSnapshot = generateConfigFromAnswers(
        session.playbook.playbookId,
        answers,
        onboardingConfig,
      );

      await db.playbookOnboardingSession.update({
        where: { id: session.id },
        data: {
          currentStep: newCurrentStep,
          answers: JSON.stringify(answers),
          configSnapshot: JSON.stringify(configSnapshot),
          status: OnboardingSessionStatusEnum.COMPLETED,
          completedAt: new Date(),
        },
      });

      return {
        success: true,
        sessionId,
        stepId,
        valid: true,
        nextStep: undefined, // No more steps
        progress: computeProgress(newCurrentStep, onboardingConfig.steps),
        sessionStatus: OnboardingSessionStatusEnum.COMPLETED,
      };
    }

    // Not the last step — update and continue
    await db.playbookOnboardingSession.update({
      where: { id: session.id },
      data: {
        currentStep: newCurrentStep,
        answers: JSON.stringify(answers),
      },
    });

    const nextStep = onboardingConfig.steps[newCurrentStep];

    return {
      success: true,
      sessionId,
      stepId,
      valid: true,
      nextStep,
      progress: computeProgress(newCurrentStep, onboardingConfig.steps),
      sessionStatus: OnboardingSessionStatusEnum.IN_PROGRESS,
    };
  } catch (error) {
    return {
      success: false,
      sessionId,
      stepId,
      valid: false,
      validationError: `Processing error: ${error instanceof Error ? error.message : String(error)}`,
      progress: { totalSteps: 0, completedSteps: 0, percentage: 0, remainingStepIds: [], remainingStepTitles: [] },
      sessionStatus: OnboardingSessionStatusEnum.IN_PROGRESS,
    };
  }
}

// ─── Completion ──────────────────────────────────────────────────────

/**
 * Complete an onboarding session.
 * Validates all required steps are answered, generates the final config
 * snapshot, and optionally triggers playbook activation.
 */
export async function completeOnboarding(
  sessionId: string,
): Promise<OnboardingCompletionResult> {
  try {
    const session = await db.playbookOnboardingSession.findFirst({
      where: { sessionId },
      include: { playbook: true },
    });

    if (!session) {
      return {
        success: false,
        sessionId,
        configSnapshot: {},
        warnings: [],
        error: `Session "${sessionId}" not found`,
      };
    }

    if (session.status === OnboardingSessionStatusEnum.COMPLETED) {
      // Already completed — return existing config
      const existingConfig = JSON.parse(session.configSnapshot || "{}");
      return {
        success: true,
        sessionId,
        configSnapshot: existingConfig,
        warnings: ["Session was already completed"],
      };
    }

    if (session.status === OnboardingSessionStatusEnum.ABANDONED) {
      return {
        success: false,
        sessionId,
        configSnapshot: {},
        warnings: [],
        error: "Cannot complete an abandoned session",
      };
    }

    // Parse onboarding config and answers
    const onboardingConfig: PlaybookOnboardingConfig = JSON.parse(session.playbook.onboarding);
    const answers: Record<string, unknown> = JSON.parse(session.answers);

    // Validate all required steps have been answered
    const warnings: string[] = [];
    const missingRequired: string[] = [];

    for (const step of onboardingConfig.steps) {
      if (step.required && (answers[step.field] === undefined || answers[step.field] === null)) {
        missingRequired.push(step.id);
      }
    }

    if (missingRequired.length > 0) {
      return {
        success: false,
        sessionId,
        configSnapshot: {},
        warnings,
        error: `Missing required steps: ${missingRequired.join(", ")}`,
      };
    }

    // Check for optional unanswered steps and apply defaults
    for (const step of onboardingConfig.steps) {
      if (answers[step.field] === undefined || answers[step.field] === null) {
        if (step.default_value !== undefined && step.default_value !== null) {
          answers[step.field] = step.default_value;
          warnings.push(`Applied default value for optional step "${step.title}" (${step.field})`);
        } else {
          warnings.push(`Optional step "${step.title}" (${step.field}) has no answer and no default`);
        }
      }
    }

    // Generate final config snapshot
    const configSnapshot = generateConfigFromAnswers(
      session.playbook.playbookId,
      answers,
      onboardingConfig,
    );

    // Mark session as completed
    await db.playbookOnboardingSession.update({
      where: { id: session.id },
      data: {
        status: OnboardingSessionStatusEnum.COMPLETED,
        answers: JSON.stringify(answers),
        configSnapshot: JSON.stringify(configSnapshot),
        completedAt: new Date(),
      },
    });

    return {
      success: true,
      sessionId,
      configSnapshot,
      warnings,
    };
  } catch (error) {
    return {
      success: false,
      sessionId,
      configSnapshot: {},
      warnings: [],
      error: `Completion failed: ${error instanceof Error ? error.message : String(error)}`,
    };
  }
}

// ─── Abandon ─────────────────────────────────────────────────────────

/**
 * Abandon an onboarding session.
 * Marks the session as abandoned so it can no longer be processed.
 */
export async function abandonOnboarding(sessionId: string): Promise<void> {
  try {
    const session = await db.playbookOnboardingSession.findFirst({
      where: { sessionId },
    });

    if (!session) {
      throw new Error(`Session "${sessionId}" not found`);
    }

    if (session.status === OnboardingSessionStatusEnum.COMPLETED) {
      throw new Error("Cannot abandon a completed session");
    }

    await db.playbookOnboardingSession.update({
      where: { id: session.id },
      data: {
        status: OnboardingSessionStatusEnum.ABANDONED,
      },
    });
  } catch (error) {
    throw new Error(
      `Failed to abandon onboarding: ${error instanceof Error ? error.message : String(error)}`,
    );
  }
}

// ─── Config Generation ───────────────────────────────────────────────

/**
 * Transform raw onboarding answers into a structured configuration.
 * Applies defaults for unanswered optional questions.
 * Can be called without a DB lookup if onboardingConfig is provided.
 */
export function generateConfigFromAnswers(
  playbookId: string,
  answers: Record<string, unknown>,
  onboardingConfig?: PlaybookOnboardingConfig,
): Record<string, unknown> {
  // Build structured config from answers
  const config: Record<string, unknown> = {
    _playbookId: playbookId,
    _generatedAt: new Date().toISOString(),
  };

  // If onboarding config is provided, we can apply defaults for missing fields
  if (onboardingConfig) {
    for (const step of onboardingConfig.steps) {
      const value = answers[step.field];
      if (value !== undefined && value !== null) {
        config[step.field] = value;
      } else if (step.default_value !== undefined && step.default_value !== null) {
        config[step.field] = step.default_value;
      } else if (step.required) {
        // Required field without answer — mark as null
        config[step.field] = null;
      }
      // Optional field without answer or default — omit from config
    }
  } else {
    // No onboarding config — just use the answers as-is
    for (const [key, value] of Object.entries(answers)) {
      if (value !== undefined && value !== null) {
        config[key] = value;
      }
    }
  }

  return config;
}

// ─── Progress ────────────────────────────────────────────────────────

/**
 * Get progress information for an onboarding session.
 */
export async function getOnboardingProgress(
  sessionId: string,
): Promise<OnboardingProgress> {
  try {
    const session = await db.playbookOnboardingSession.findFirst({
      where: { sessionId },
      include: { playbook: true },
    });

    if (!session) {
      return {
        totalSteps: 0,
        completedSteps: 0,
        percentage: 0,
        remainingStepIds: [],
        remainingStepTitles: [],
      };
    }

    const onboardingConfig: PlaybookOnboardingConfig = JSON.parse(session.playbook.onboarding);

    return computeProgress(session.currentStep, onboardingConfig.steps);
  } catch (error) {
    return {
      totalSteps: 0,
      completedSteps: 0,
      percentage: 0,
      remainingStepIds: [],
      remainingStepTitles: [],
    };
  }
}

// ─── Internal Helpers ────────────────────────────────────────────────

/**
 * Validate an answer against a step definition.
 * Returns { valid: true } or { valid: false, error: string }.
 */
function validateStepAnswer(
  step: OnboardingStep,
  answer: unknown,
): { valid: true } | { valid: false; error: string } {
  // Check required
  if (step.required && (answer === undefined || answer === null || answer === "")) {
    return { valid: false, error: `Step "${step.id}" is required but no answer was provided` };
  }

  // Skip further validation for optional unanswered steps
  if (answer === undefined || answer === null) {
    return { valid: true };
  }

  // Type-specific validation
  switch (step.type as OnboardingStepType) {
    case OnboardingStepTypeEnum.SELECTION: {
      // Answer must be one of the defined options
      if (step.options && step.options.length > 0) {
        const validValues = step.options.map((o) => o.value);
        if (!validValues.includes(String(answer))) {
          return {
            valid: false,
            error: `Invalid selection "${String(answer)}". Valid options: ${validValues.join(", ")}`,
          };
        }
      }
      break;
    }

    case OnboardingStepTypeEnum.QUESTION: {
      // Answer should be a non-empty string for question type
      if (typeof answer !== "string" && typeof answer !== "number" && typeof answer !== "boolean") {
        return {
          valid: false,
          error: `Step "${step.id}" expects a text/number/boolean answer, got ${typeof answer}`,
        };
      }
      break;
    }

    case OnboardingStepTypeEnum.CONFIRMATION: {
      // Answer should be a boolean
      if (typeof answer !== "boolean") {
        return {
          valid: false,
          error: `Step "${step.id}" expects a boolean confirmation, got ${typeof answer}`,
        };
      }
      break;
    }

    case OnboardingStepTypeEnum.AUTO_CONFIG: {
      // Auto-config steps typically don't require user input
      // But if an answer is provided, accept any value
      break;
    }

    default: {
      // Unknown step type — accept the answer
      break;
    }
  }

  return { valid: true };
}

/**
 * Compute progress from current step index and step definitions.
 */
function computeProgress(
  currentStep: number,
  steps: OnboardingStep[],
): OnboardingProgress {
  const totalSteps = steps.length;
  const completedSteps = Math.min(currentStep, totalSteps);
  const percentage = totalSteps > 0 ? Math.round((completedSteps / totalSteps) * 100) : 0;

  const remainingSteps = steps.slice(currentStep);
  const remainingStepIds = remainingSteps.map((s) => s.id);
  const remainingStepTitles = remainingSteps.map((s) => s.title);

  return {
    totalSteps,
    completedSteps,
    percentage,
    remainingStepIds,
    remainingStepTitles,
  };
}
