// ─── Onboarding Wizard Core — Session Lifecycle ─────────────────────
// create → step → step → ... → complete | abandon

import { randomUUID } from "crypto";
import { db } from "@/lib/db";
import type { OnboardingSession, PlaybookOnboardingConfig } from "../types";
import { OnboardingSessionStatus as OnboardingSessionStatusEnum } from "../types";
import type { OnboardingStepResult } from "./types";
import { validateStepAnswer, computeProgress, generateConfigFromAnswers } from "./_steps";

const EMPTY_PROGRESS = { totalSteps: 0, completedSteps: 0, percentage: 0, remainingStepIds: [], remainingStepTitles: [] };

/** Create a new onboarding session for a playbook. */
export async function createOnboardingSession(
  playbookId: string,
  tenantId?: string,
): Promise<OnboardingSession> {
  try {
    const playbook = await db.playbook.findFirst({ where: { playbookId } });
    if (!playbook) throw new Error(`Playbook "${playbookId}" not found`);
    if (!playbook.isActive) throw new Error(`Playbook "${playbookId}" is not active`);
    const onboardingConfig: PlaybookOnboardingConfig = JSON.parse(playbook.onboarding);
    if (!onboardingConfig.steps || onboardingConfig.steps.length === 0) throw new Error(`Playbook "${playbookId}" has no onboarding steps defined`);
    const sessionId = `onb_${Date.now().toString(36)}_${randomUUID().slice(0, 8)}`;
    const answers: Record<string, unknown> = {};
    for (const step of onboardingConfig.steps) {
      if (step.default_value !== undefined && step.default_value !== null) answers[step.field] = step.default_value;
    }
    const now = new Date().toISOString();
    await db.playbookOnboardingSession.create({
      data: { playbookDbId: playbook.id, tenantId: tenantId ?? null, sessionId, status: OnboardingSessionStatusEnum.IN_PROGRESS, currentStep: 0, answers: JSON.stringify(answers), configSnapshot: "{}" },
    });
    return { playbookId, sessionId, status: OnboardingSessionStatusEnum.IN_PROGRESS, answers, config_snapshot: undefined, created: now, updated: now };
  } catch (error) {
    throw new Error(`Failed to create onboarding session: ${error instanceof Error ? error.message : String(error)}`);
  }
}

/** Load an onboarding session from DB by session ID. */
export async function getOnboardingSession(sessionId: string): Promise<OnboardingSession | null> {
  try {
    const session = await db.playbookOnboardingSession.findFirst({ where: { sessionId }, include: { playbook: { select: { playbookId: true } } } });
    if (!session) return null;
    return {
      playbookId: session.playbook.playbookId,
      sessionId: session.sessionId,
      status: session.status as OnboardingSession["status"],
      answers: JSON.parse(session.answers),
      config_snapshot: session.configSnapshot && session.configSnapshot !== "{}" ? JSON.parse(session.configSnapshot) : undefined,
      created: session.createdAt.toISOString(),
      updated: session.updatedAt.toISOString(),
    };
  } catch (error) {
    throw new Error(`Failed to get onboarding session: ${error instanceof Error ? error.message : String(error)}`);
  }
}

/** Process an answer for a specific onboarding step. */
export async function processOnboardingStep(
  sessionId: string,
  stepId: string,
  answer: unknown,
): Promise<OnboardingStepResult> {
  try {
    const session = await db.playbookOnboardingSession.findFirst({ where: { sessionId }, include: { playbook: true } });
    if (!session) return { success: false, sessionId, stepId, valid: false, validationError: `Session "${sessionId}" not found`, progress: EMPTY_PROGRESS, sessionStatus: OnboardingSessionStatusEnum.ABANDONED };
    if (session.status !== OnboardingSessionStatusEnum.IN_PROGRESS) return { success: false, sessionId, stepId, valid: false, validationError: `Session is ${session.status}, cannot process steps`, progress: computeProgress(0, []), sessionStatus: session.status as OnboardingSession["status"] };
    const onboardingConfig: PlaybookOnboardingConfig = JSON.parse(session.playbook.onboarding);
    const answers: Record<string, unknown> = JSON.parse(session.answers);
    const stepIndex = onboardingConfig.steps.findIndex((s) => s.id === stepId);
    if (stepIndex === -1) return { success: false, sessionId, stepId, valid: false, validationError: `Step "${stepId}" not found in playbook onboarding`, progress: computeProgress(session.currentStep, onboardingConfig.steps), sessionStatus: OnboardingSessionStatusEnum.IN_PROGRESS };
    const step = onboardingConfig.steps[stepIndex];
    const validation = validateStepAnswer(step, answer);
    if (!validation.valid) return { success: false, sessionId, stepId, valid: false, validationError: validation.error, progress: computeProgress(session.currentStep, onboardingConfig.steps), sessionStatus: OnboardingSessionStatusEnum.IN_PROGRESS };
    answers[step.field] = answer;
    const newCurrentStep = Math.min(stepIndex + 1, onboardingConfig.steps.length);
    const isLastStep = newCurrentStep >= onboardingConfig.steps.length;
    if (isLastStep) {
      const configSnapshot = generateConfigFromAnswers(session.playbook.playbookId, answers, onboardingConfig);
      await db.playbookOnboardingSession.update({ where: { id: session.id }, data: { currentStep: newCurrentStep, answers: JSON.stringify(answers), configSnapshot: JSON.stringify(configSnapshot), status: OnboardingSessionStatusEnum.COMPLETED, completedAt: new Date() } });
      return { success: true, sessionId, stepId, valid: true, nextStep: undefined, progress: computeProgress(newCurrentStep, onboardingConfig.steps), sessionStatus: OnboardingSessionStatusEnum.COMPLETED };
    }
    await db.playbookOnboardingSession.update({ where: { id: session.id }, data: { currentStep: newCurrentStep, answers: JSON.stringify(answers) } });
    return { success: true, sessionId, stepId, valid: true, nextStep: onboardingConfig.steps[newCurrentStep], progress: computeProgress(newCurrentStep, onboardingConfig.steps), sessionStatus: OnboardingSessionStatusEnum.IN_PROGRESS };
  } catch (error) {
    return { success: false, sessionId, stepId, valid: false, validationError: `Processing error: ${error instanceof Error ? error.message : String(error)}`, progress: EMPTY_PROGRESS, sessionStatus: OnboardingSessionStatusEnum.IN_PROGRESS };
  }
}
