// ─── Zenic-Agents v3 — Policy Namespace Engine ────────────────────────
// Multi-tenant policy scoping with hierarchical inheritance.
// Phase 4: Declarative Versioned Policy Engine — Namespace Module
//
// Design Patterns:
//   - Chain of Responsibility: namespace hierarchy evaluation
//   - Strategy: resolution strategies (local_first, priority_based, deny_wins, most_restrictive)
//   - Composite: namespace tree with parent-child relationships

import { db } from "@/lib/db";
import type {
  PolicyDocument,
  PolicyEvaluationRequest,
  PolicyEvaluationResult,
  PolicyEffectV2,
  PolicyStatement,
} from "./types";
import type {
  PolicyNamespace,
  NamespaceHierarchy,
  NamespaceResolutionStrategy,
  NamespaceIsolationLevel,
  NamespaceResolutionResult,
  ConflictResolutionStrategy,
} from "./types";
import {
  NamespaceResolutionStrategy as ResolutionStrategy,
  ConflictResolutionStrategy as ConflictStrategy,
  NAMESPACE_API_VERSION as NS_API_VERSION,
  NAMESPACE_KIND as NS_KIND,
} from "./types";
import { PolicyEvaluator, getPolicyEvaluator } from "./evaluator";

// ─── Namespace Engine Error Types ─────────────────────────────────────

/** Error thrown when a namespace operation fails validation */
export class NamespaceError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "NamespaceError";
  }
}

// ─── DB Record Mapper ─────────────────────────────────────────────────

/** Internal representation of a namespace DB row mapped to typed fields */
interface NamespaceDbRecord {
  id: string;
  namespaceId: string;
  name: string;
  description: string;
  tenantId: string;
  parentNamespaceId: string | null;
  path: string;
  labels: Record<string, string>;
  inheritFromParent: boolean;
  maxInheritanceDepth: number;
  parentChildResolution: ConflictResolutionStrategy;
  childCanOverrideParentDeny: boolean;
  childCanAddAllow: boolean;
  resolutionStrategy: NamespaceResolutionStrategy;
  isolationLevel: NamespaceIsolationLevel;
  isActive: boolean;
  createdAt: Date;
  updatedAt: Date;
}

/** Updates that can be applied to a namespace */
export interface NamespaceUpdateRequest {
  name?: string;
  description?: string;
  labels?: Record<string, string>;
  inheritFromParent?: boolean;
  maxInheritanceDepth?: number;
  parentChildResolution?: ConflictResolutionStrategy;
  childCanOverrideParentDeny?: boolean;
  childCanAddAllow?: boolean;
  resolutionStrategy?: NamespaceResolutionStrategy;
  isolationLevel?: NamespaceIsolationLevel;
}

/** A single step in the namespace evaluation trace */
interface NamespaceEvaluationTrace {
  namespaceId: string;
  namespacePath: string;
  depth: number;
  policiesEvaluated: number;
  result: PolicyEvaluationResult | null;
  inherited: boolean;
}

// ─── Helper: Map DB Row to NamespaceDbRecord ──────────────────────────

function mapDbToRecord(row: {
  id: string;
  namespaceId: string;
  name: string;
  description: string;
  tenantId: string;
  parentNamespaceId: string | null;
  path: string;
  labels: string;
  inheritFromParent: boolean;
  maxInheritanceDepth: number;
  parentChildResolution: string;
  childCanOverrideParentDeny: boolean;
  childCanAddAllow: boolean;
  resolutionStrategy: string;
  isolationLevel: string;
  isActive: boolean;
  createdAt: Date;
  updatedAt: Date;
}): NamespaceDbRecord {
  return {
    id: row.id,
    namespaceId: row.namespaceId,
    name: row.name,
    description: row.description,
    tenantId: row.tenantId,
    parentNamespaceId: row.parentNamespaceId,
    path: row.path,
    labels: JSON.parse(row.labels),
    inheritFromParent: row.inheritFromParent,
    maxInheritanceDepth: row.maxInheritanceDepth,
    parentChildResolution: row.parentChildResolution as ConflictResolutionStrategy,
    childCanOverrideParentDeny: row.childCanOverrideParentDeny,
    childCanAddAllow: row.childCanAddAllow,
    resolutionStrategy: row.resolutionStrategy as NamespaceResolutionStrategy,
    isolationLevel: row.isolationLevel as NamespaceIsolationLevel,
    isActive: row.isActive,
    createdAt: row.createdAt,
    updatedAt: row.updatedAt,
  };
}

// ─── Helper: Map DB Record to PolicyNamespace ─────────────────────────

function mapRecordToPolicyNamespace(rec: NamespaceDbRecord): PolicyNamespace {
  return {
    apiVersion: NS_API_VERSION,
    kind: NS_KIND,
    metadata: {
      id: rec.namespaceId,
      name: rec.name,
      description: rec.description,
      tenantId: rec.tenantId,
