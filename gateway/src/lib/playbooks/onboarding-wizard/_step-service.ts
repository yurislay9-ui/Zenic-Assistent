// ─── Onboarding Wizard Step Service ────────────────────────────────────
// Step processing and completion operations.
// Extracted from onboarding-wizard.ts.

import { db } from "@/lib/db";
import type {
  OnboardingSessionStatus,
  PlaybookOnboardingConfig,
} from "../types";
import {
  OnboardingSessionStatus as OnboardingSessionStatusEnum,
} from "../types";
import type {
  OnboardingStepResult,
  OnboardingCompletionResult,
} from "./_types";
import { validateStepAnswer, computeProgress, generateConfigFromAnswers } from "./_utils";

/**
 * Process an answer for a specific onboarding step.
 */
export async function processOnboardingStep(
  sessionId: string,
  stepId: string,
  answer: unknown,
): Promise<OnboardingStepResult> {
  try {
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

    const onboardingConfig: PlaybookOnboardingConfig = JSON.parse(session.playbook.onboarding);
    const answers: Record<string, unknown> = JSON.parse(session.answers);

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

    answers[step.field] = answer;

    const newCurrentStep = Math.min(stepIndex + 1, onboardingConfig.steps.length);
    const isLastStep = newCurrentStep >= onboardingConfig.steps.length;

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
        nextStep: undefined,
        progress: computeProgress(newCurrentStep, onboardingConfig.steps),
        sessionStatus: OnboardingSessionStatusEnum.COMPLETED,
      };
    }

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

/**
 * Complete an onboarding session.
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

    const onboardingConfig: PlaybookOnboardingConfig = JSON.parse(session.playbook.onboarding);
    const answers: Record<string, unknown> = JSON.parse(session.answers);

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

    const configSnapshot = generateConfigFromAnswers(
      session.playbook.playbookId,
      answers,
      onboardingConfig,
    );

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

/**
 * Abandon an onboarding session.
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
