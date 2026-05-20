// ─── Onboarding Step Validation, Progress & Session Helpers ──────────
// Pure functions and DB-backed operations that support the wizard lifecycle.

import { db } from "@/lib/db";
import type { OnboardingStep, PlaybookOnboardingConfig } from "../types";
import { OnboardingSessionStatus as OnboardingSessionStatusEnum, OnboardingStepType as OnboardingStepTypeEnum } from "../types";
import type { OnboardingCompletionResult, OnboardingProgress } from "./types";

/**
 * Validate an answer against a step definition.
 */
export function validateStepAnswer(
  step: OnboardingStep,
  answer: unknown,
): { valid: true } | { valid: false; error: string } {
  if (step.required && (answer === undefined || answer === null || answer === "")) {
    return { valid: false, error: `Step "${step.id}" is required but no answer was provided` };
  }
  if (answer === undefined || answer === null) {
    return { valid: true };
  }
  switch (step.type as keyof typeof OnboardingStepTypeEnum) {
    case OnboardingStepTypeEnum.SELECTION: {
      if (step.options && step.options.length > 0) {
        const validValues = step.options.map((o) => o.value);
        if (!validValues.includes(String(answer))) {
          return { valid: false, error: `Invalid selection "${String(answer)}". Valid options: ${validValues.join(", ")}` };
        }
      }
      break;
    }
    case OnboardingStepTypeEnum.QUESTION: {
      if (typeof answer !== "string" && typeof answer !== "number" && typeof answer !== "boolean") {
        return { valid: false, error: `Step "${step.id}" expects a text/number/boolean answer, got ${typeof answer}` };
      }
      break;
    }
    case OnboardingStepTypeEnum.CONFIRMATION: {
      if (typeof answer !== "boolean") {
        return { valid: false, error: `Step "${step.id}" expects a boolean confirmation, got ${typeof answer}` };
      }
      break;
    }
    case OnboardingStepTypeEnum.AUTO_CONFIG:
      break;
    default:
      break;
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
  return {
    totalSteps,
    completedSteps,
    percentage,
    remainingStepIds: remainingSteps.map((s) => s.id),
    remainingStepTitles: remainingSteps.map((s) => s.title),
  };
}

/**
 * Transform raw onboarding answers into a structured configuration.
 */
export function generateConfigFromAnswers(
  playbookId: string,
  answers: Record<string, unknown>,
  onboardingConfig?: PlaybookOnboardingConfig,
): Record<string, unknown> {
  const config: Record<string, unknown> = { _playbookId: playbookId, _generatedAt: new Date().toISOString() };
  if (onboardingConfig) {
    for (const step of onboardingConfig.steps) {
      const value = answers[step.field];
      if (value !== undefined && value !== null) config[step.field] = value;
      else if (step.default_value !== undefined && step.default_value !== null) config[step.field] = step.default_value;
      else if (step.required) config[step.field] = null;
    }
  } else {
    for (const [key, value] of Object.entries(answers)) {
      if (value !== undefined && value !== null) config[key] = value;
    }
  }
  return config;
}

const EMPTY_PROGRESS: OnboardingProgress = { totalSteps: 0, completedSteps: 0, percentage: 0, remainingStepIds: [], remainingStepTitles: [] };

/**
 * Complete an onboarding session.
 */
export async function completeOnboarding(sessionId: string): Promise<OnboardingCompletionResult> {
  try {
    const session = await db.playbookOnboardingSession.findFirst({ where: { sessionId }, include: { playbook: true } });
    if (!session) return { success: false, sessionId, configSnapshot: {}, warnings: [], error: `Session "${sessionId}" not found` };
    if (session.status === OnboardingSessionStatusEnum.COMPLETED) {
      return { success: true, sessionId, configSnapshot: JSON.parse(session.configSnapshot || "{}"), warnings: ["Session was already completed"] };
    }
    if (session.status === OnboardingSessionStatusEnum.ABANDONED) {
      return { success: false, sessionId, configSnapshot: {}, warnings: [], error: "Cannot complete an abandoned session" };
    }
    const onboardingConfig: PlaybookOnboardingConfig = JSON.parse(session.playbook.onboarding);
    const answers: Record<string, unknown> = JSON.parse(session.answers);
    const warnings: string[] = [];
    const missingRequired: string[] = [];
    for (const step of onboardingConfig.steps) {
      if (step.required && (answers[step.field] === undefined || answers[step.field] === null)) missingRequired.push(step.id);
    }
    if (missingRequired.length > 0) {
      return { success: false, sessionId, configSnapshot: {}, warnings, error: `Missing required steps: ${missingRequired.join(", ")}` };
    }
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
    const configSnapshot = generateConfigFromAnswers(session.playbook.playbookId, answers, onboardingConfig);
    await db.playbookOnboardingSession.update({
      where: { id: session.id },
      data: { status: OnboardingSessionStatusEnum.COMPLETED, answers: JSON.stringify(answers), configSnapshot: JSON.stringify(configSnapshot), completedAt: new Date() },
    });
    return { success: true, sessionId, configSnapshot, warnings };
  } catch (error) {
    return { success: false, sessionId, configSnapshot: {}, warnings: [], error: `Completion failed: ${error instanceof Error ? error.message : String(error)}` };
  }
}

/**
 * Abandon an onboarding session.
 */
export async function abandonOnboarding(sessionId: string): Promise<void> {
  try {
    const session = await db.playbookOnboardingSession.findFirst({ where: { sessionId } });
    if (!session) throw new Error(`Session "${sessionId}" not found`);
    if (session.status === OnboardingSessionStatusEnum.COMPLETED) throw new Error("Cannot abandon a completed session");
    await db.playbookOnboardingSession.update({ where: { id: session.id }, data: { status: OnboardingSessionStatusEnum.ABANDONED } });
  } catch (error) {
    throw new Error(`Failed to abandon onboarding: ${error instanceof Error ? error.message : String(error)}`);
  }
}

/**
 * Get progress information for an onboarding session.
 */
export async function getOnboardingProgress(sessionId: string): Promise<OnboardingProgress> {
  try {
    const session = await db.playbookOnboardingSession.findFirst({ where: { sessionId }, include: { playbook: true } });
    if (!session) return EMPTY_PROGRESS;
    const onboardingConfig: PlaybookOnboardingConfig = JSON.parse(session.playbook.onboarding);
    return computeProgress(session.currentStep, onboardingConfig.steps);
  } catch {
    return EMPTY_PROGRESS;
  }
}
