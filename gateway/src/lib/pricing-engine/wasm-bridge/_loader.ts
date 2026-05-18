// ─── WASM Bridge — Loader ────────────────────────────────────────────────────
// Handles WASM module loading, state management, and fallback detection.

import type { WasmModule } from "./types";

// ═══════════════════════════════════════════════════════════════════════════
// WASM Loading State
// ═══════════════════════════════════════════════════════════════════════════

/** @internal Shared WASM module instance — consumed by _executor.ts */
export let wasmModule: WasmModule | null = null;

let wasmLoadAttempted = false;
let wasmLoadError: string | null = null;

/**
 * Attempt to load the WASM module from the compiled Rust package.
 * Returns true if WASM was loaded successfully, false if using TS fallback.
 */
export async function initWasm(): Promise<boolean> {
  if (wasmModule) return true;
  if (wasmLoadAttempted) return false;

  wasmLoadAttempted = true;

  try {
    // Dynamic import of the WASM module from the Rust engine package
    // NOTE: rust-engine/ directory doesn't exist yet. This will fail
    // gracefully and the TypeScript fallback will be used instead.
    // When the Rust pricing engine is built with wasm-pack, this path
    // should be updated to point to the generated pkg/ directory.
    const wasmPkg = (await import(
      /* webpackIgnore: true */
      "../../../rust-engine/pkg/zenic_pricing_engine.js"
    )) as unknown as WasmModule;
    wasmModule = wasmPkg;
    wasmLoadError = null;
    return true;
  } catch (err) {
    wasmLoadError = err instanceof Error ? err.message : String(err);
    wasmModule = null;
    return false;
  }
}

/**
 * Returns whether the WASM engine is currently active.
 */
export function isWasmActive(): boolean {
  return wasmModule !== null;
}

/**
 * Returns the WASM load error if the TS fallback is being used.
 */
export function getWasmLoadError(): string | null {
  return wasmLoadError;
}

/**
 * Reset WASM state (useful for testing or re-initialization).
 */
export function resetWasm(): void {
  wasmModule = null;
  wasmLoadAttempted = false;
  wasmLoadError = null;
}
