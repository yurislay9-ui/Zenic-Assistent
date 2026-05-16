// ─── Zenic-Agents v3 — Adapters Barrel Export ───────────────────────

export {
  registerOpenAITool,
  registerOpenAITools,
} from "./openai-adapter";

export type {
  OpenAIFunction,
  OpenAITool,
  OpenAIParameterProperty,
  OpenAIToolOptions,
} from "./openai-adapter";

export {
  ZENIC_EXECUTOR_TYPES,
  registerNativeExecutors,
} from "./native-adapter";

export type { ZenicExecutorType } from "./native-adapter";
