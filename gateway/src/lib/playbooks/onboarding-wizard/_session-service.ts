// ─── Onboarding Wizard Service ─────────────────────────────────────────
// Database-backed session lifecycle operations.
// Extracted from onboarding-wizard.ts.

import { randomUUID } from "crypto";
import { db } from "@/lib/db";
import type {
  OnboardingSession,
  OnboardingSessionStatus,
  PlaybookOnboardingConfig,
} from "../types";
import {
  OnboardingSessionStatus as OnboardingSessionStatusEnum,
} from "../types";
import type {
  OnboardingStepResult,
  OnboardingCompletionResult,
  OnboardingProgress,
} from "./_types";
import { validateStepAnswer, computeProgress, generateConfigFromAnswers } from "./_utils";

/**
 * Create a new onboarding session for a playbook.
 */
export async function createOnboardingSession(
  playbookId: string,
  tenantId?: string,
): Promise<OnboardingSession> {
  try {
    const playbook = await db.playbook.findFirst({
      where: { playbookId },
    });

    if (!playbook) {
      throw new Error(`Playbook "${playbookId}" not found`);
    }

    if (!playbook.isActive) {
      throw new Error(`Playbook "${playbookId}" is not active`);
    }

    const onboardingConfig: PlaybookOnboardingConfig = JSON.parse(playbook.onboarding);

    if (!onboardingConfig.steps || onboardingConfig.steps.length === 0) {
      throw new Error(`Playbook "${playbookId}" has no onboarding steps defined`);
    }

    const sessionId = `onb_${Date.now().toString(36)}_${randomUUID().slice(0, 8)}`;

    const answers: Record<string, unknown> = {};
    for (const step of onboardingConfig.steps) {
      if (step.default_value !== undefined && step.default_value !== null) {
        answers[step.field] = step.default_value;
      }
    }

    const now = new Date().toISOString();

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
