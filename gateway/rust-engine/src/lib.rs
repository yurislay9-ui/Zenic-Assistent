// ─── Zenic-Agents v3 — Compiled Pricing Engine (Rust → WASM) ────────────
// USDT TRC20 ONLY. All pricing logic is compiled and tamper-proof.
// Saga Pattern for subscription lifecycle management.
//
// This file is a thin re-export root. All implementation lives in:
//   - types/        : core data types and domain logic
//   - saga/         : saga pattern definitions, execution, pricing
//   - lib_parts/    : WASM-bindgen export functions (split by domain)

mod types;
mod saga;
mod lib_parts;

use lib_parts::*;
