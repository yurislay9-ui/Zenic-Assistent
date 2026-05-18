// ─── Zenic-Agents v3 — Policy Impact Analysis Engine ────────────────────
// Phase 4: Declarative Versioned Policy Engine — Impact Analysis Module
//
// Analyzes the impact of changing a policy by:
//   1. Loading the target policy from DB
//   2. Finding direct and indirect dependencies (Visitor pattern)
//   3. Predicting downstream evaluation changes (Strategy pattern)
//   4. Calculating blast radius with risk scoring
//   5. Persisting analysis results to DB
//
// Design Patterns:
//   - Visitor: DependencyGraphVisitor traverses the dependency graph
//   - Strategy: DepthStrategy determines analysis depth (quick/standard/deep)
//   - Composite: DependencyNode composes dependency tree with children

import { db } from "@/lib/db";
import type {
  PolicyDocument,
  PolicyEffectV2,
} from "./types";
import type {
  ImpactAnalysisRequest,
  ImpactAnalysisDepth,
  ImpactAnalysisResult,
  DependencyRef,
  DependencyType,
  AffectedSetRef,
  AffectedPlaybookRef,
  AffectedToolRef,
  BlastRadius,
  ImpactCategory,
  DownstreamChange,
  SimulationRiskLevel,
  ConflictSeverity,
  PolicySetEntry,
} from "./types";
import {
  ImpactAnalysisDepth as ImpactAnalysisDepthValues,
  DependencyType as DependencyTypeValues,
  SimulationRiskLevel as SimulationRiskLevelValues,
  ConflictSeverity as ConflictSeverityValues,
} from "./types";

// ─── Composite: Dependency Node ─────────────────────────────────────────

/** A node in the dependency tree (Composite pattern) */
interface DependencyNode {
  /** Unique identifier for this node */
  id: string;
  /** Type of resource */
  type: "policy" | "policy_set" | "playbook" | "tool" | "approval";
  /** Human-readable name */
  name: string;
  /** Dependency type from parent */
  dependencyType: DependencyType;
  /** Whether this is a hard dependency */
  hardDependency: boolean;
  /** Child nodes (indirect dependencies) */
  children: DependencyNode[];
  /** Extra typed data attached to this node (e.g., AffectedSetRef, AffectedToolRef) */
  data?: unknown;
}

/** Build a DependencyRef from a DependencyNode */
function nodeToRef(node: DependencyNode): DependencyRef {
  return {
    id: node.id,
    type: node.type,
    name: node.name,
    dependencyType: node.dependencyType,
    hardDependency: node.hardDependency,
  };
}

// ─── Strategy: Depth Analysis Strategies ────────────────────────────────

/** Strategy interface for analysis depth */
interface DepthStrategy {
  /** Whether to include indirect dependencies */
  includeIndirect: boolean;
  /** Maximum levels of indirection (0 = direct only, -1 = unlimited) */
  maxIndirectionLevels: number;
  /** Whether to predict downstream tool verdict changes */
  predictToolChanges: boolean;
  /** Whether to include playbook compliance score changes */
  includeComplianceChanges: boolean;
}

/** Strategy configuration per analysis depth */
const DEPTH_STRATEGIES: Record<ImpactAnalysisDepth, DepthStrategy> = {
  [ImpactAnalysisDepthValues.QUICK]: {
    includeIndirect: false,
    maxIndirectionLevels: 0,
    predictToolChanges: true,
    includeComplianceChanges: false,
  },
  [ImpactAnalysisDepthValues.STANDARD]: {
    includeIndirect: true,
    maxIndirectionLevels: 1,
    predictToolChanges: true,
