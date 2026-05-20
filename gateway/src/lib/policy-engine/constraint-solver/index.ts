// Constraint Solver — split from original constraint-solver.ts

export * from './types';
export * from './helpers';
// Note: ranges.ts is a backward-compat re-export barrel for direct imports only.
// Do NOT add `export * from './ranges'` here — it would duplicate exports from helpers.
export * from './consistency';
export * from './solvers';
export * from './verification';
export * from './_reachability';
export * from './_persistence';
