// ─── Onboarding Wizard Barrel Export ─────────────────────────────────
// Preserves `import { ... } from "@/lib/playbooks/onboarding-wizard"`

export {
  createOnboardingSession,
  getOnboardingSession,
  processOnboardingStep,
} from "./_wizard";

export {
  completeOnboarding,
  abandonOnboarding,
  generateConfigFromAnswers,
  getOnboardingProgress,
} from "./_steps";

export type {
  OnboardingStepResult,
  OnboardingCompletionResult,
  OnboardingProgress,
} from "./types";
