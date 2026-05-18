// ─── Onboarding Wizard Utilities ───────────────────────────────────────
// Pure functions for validation, progress, and config generation.
// Extracted from onboarding-wizard.ts.

import type {
  OnboardingStep,
  OnboardingStepType,
  PlaybookOnboardingConfig,
} from "../types";
import { OnboardingStepType as OnboardingStepTypeEnum } from "../types";
import type { OnboardingProgress } from "./_types";

/**
 * Validate an answer against a step definition.
 * Returns { valid: true } or { valid: false, error: string }.
 */
export function validateStepAnswer(
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
      if (typeof answer !== "string" && typeof answer !== "number" && typeof answer !== "boolean") {
        return {
          valid: false,
          error: `Step "${step.id}" expects a text/number/boolean answer, got ${typeof answer}`,
        };
      }
      break;
    }

    case OnboardingStepTypeEnum.CONFIRMATION: {
      if (typeof answer !== "boolean") {
        return {
          valid: false,
          error: `Step "${step.id}" expects a boolean confirmation, got ${typeof answer}`,
        };
      }
      break;
    }

    case OnboardingStepTypeEnum.AUTO_CONFIG: {
      break;
    }

    default: {
      break;
    }
  }

  return { valid: true };
}

/**
 * Compute progress from current step index and step definitions.
 */
export function computeProgress(
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

/**
 * Transform raw onboarding answers into a structured configuration.
 * Applies defaults for unanswered optional questions.
 */
export function generateConfigFromAnswers(
  playbookId: string,
  answers: Record<string, unknown>,
  onboardingConfig?: PlaybookOnboardingConfig,
): Record<string, unknown> {
  const config: Record<string, unknown> = {
    _playbookId: playbookId,
    _generatedAt: new Date().toISOString(),
  };

  if (onboardingConfig) {
    for (const step of onboardingConfig.steps) {
      const value = answers[step.field];
      if (value !== undefined && value !== null) {
        config[step.field] = value;
      } else if (step.default_value !== undefined && step.default_value !== null) {
        config[step.field] = step.default_value;
      } else if (step.required) {
        config[step.field] = null;
      }
    }
  } else {
    for (const [key, value] of Object.entries(answers)) {
      if (value !== undefined && value !== null) {
        config[key] = value;
      }
    }
  }

  return config;
}
