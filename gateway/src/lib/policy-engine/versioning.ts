// ─── Zenic-Agents v3 — Policy Versioning Engine ───────────────────────
// Git-like versioning for policy documents.
// Each change creates a new version with a content hash, parent chain,
// and full snapshot. Supports rollback without downtime.
//
// Pattern: Memento — captures policy state snapshots for rollback

import { db } from "@/lib/db";
import { computeContentHash } from "./yaml-loader";
import type {
  PolicyDocument,
  PolicyVersion,
  PolicyVersionStatus,
  CreateVersionRequest,
} from "./types";

// ─── Version Creation ─────────────────────────────────────────────────

/**
 * Create a new version of a policy.
 * Automatically superseded the previous active version.
 */
export async function createVersion(request: CreateVersionRequest): Promise<PolicyVersion> {
  const { policyId, document, changeDescription, createdBy } = request;
  const contentHash = computeContentHash(document);
  const now = new Date().toISOString();

  // Find the existing policy record
  const policy = await db.declPolicy.findUnique({ where: { policyId } });
  if (!policy) {
    throw new Error(`Policy "${policyId}" not found`);
  }

  // Find the current active version (to supersede)
  const currentActive = await db.declPolicyVersion.findFirst({
    where: { declPolicyId: policy.id, status: "active" },
    orderBy: { createdAt: "desc" },
  });

  // Create the new version
  const version = await db.declPolicyVersion.create({
    data: {
      declPolicyId: policy.id,
      version: document.metadata.version,
      contentHash,
      document: JSON.stringify(document),
      status: "active",
      createdBy,
      changeDescription,
      parentVersionId: currentActive?.id ?? null,
    },
  });

  // Supersede previous active version
  if (currentActive) {
    await db.declPolicyVersion.update({
      where: { id: currentActive.id },
      data: { status: "superseded" as PolicyVersionStatus },
    });
  }

  // Update the policy record with new content
  await db.declPolicy.update({
    where: { policyId },
    data: {
      version: document.metadata.version,
      statements: JSON.stringify(document.statements),
      tests: JSON.stringify(document.tests ?? []),
      contentHash,
      labels: JSON.stringify(document.metadata.labels ?? {}),
      compliance: JSON.stringify(document.metadata.compliance ?? []),
      updatedAt: new Date(),
    },
  });

  return mapDbVersionToModel(version, document);
}

/**
 * Get a specific version of a policy.
 */
export async function getVersion(policyId: string, version: string): Promise<PolicyVersion | null> {
  const policy = await db.declPolicy.findUnique({ where: { policyId } });
  if (!policy) return null;

  const dbVersion = await db.declPolicyVersion.findUnique({
    where: {
      declPolicyId_version: { declPolicyId: policy.id, version },
    },
  });

  if (!dbVersion) return null;

  const document = JSON.parse(dbVersion.document) as PolicyDocument;
  return mapDbVersionToModel(dbVersion, document);
}

/**
 * Get all versions of a policy, ordered by creation date (newest first).
 */
export async function listVersions(
  policyId: string,
  options?: { status?: PolicyVersionStatus; limit?: number; offset?: number },
): Promise<{ versions: PolicyVersion[]; total: number }> {
  const policy = await db.declPolicy.findUnique({ where: { policyId } });
  if (!policy) return { versions: [], total: 0 };

  const where = {
    declPolicyId: policy.id,
    ...(options?.status ? { status: options.status } : {}),
  };

  const [dbVersions, total] = await Promise.all([
    db.declPolicyVersion.findMany({
      where,
      orderBy: { createdAt: "desc" },
      take: options?.limit ?? 50,
      skip: options?.offset ?? 0,
    }),
    db.declPolicyVersion.count({ where }),
  ]);

  const versions = dbVersions.map((v) => {
    const document = JSON.parse(v.document) as PolicyDocument;
    return mapDbVersionToModel(v, document);
  });

  return { versions, total };
}

/**
 * Get the version history chain (from current to oldest).
 */
export async function getVersionChain(policyId: string): Promise<PolicyVersion[]> {
  const policy = await db.declPolicy.findUnique({ where: { policyId } });
  if (!policy) return [];

  // Start from the active version and follow parentVersionId chain
  const activeVersion = await db.declPolicyVersion.findFirst({
    where: { declPolicyId: policy.id, status: "active" },
  });

  if (!activeVersion) return [];

  const chain: PolicyVersion[] = [];
  let currentId: string | null = activeVersion.id;

  while (currentId) {
    const v = await db.declPolicyVersion.findUnique({ where: { id: currentId } });
    if (!v) break;
    const document = JSON.parse(v.document) as PolicyDocument;
    chain.push(mapDbVersionToModel(v, document));
    currentId = v.parentVersionId;
  }

  return chain;
}

/**
 * Rollback a policy to a specific version.
 * Creates a new version that is a copy of the target version.
 */
export async function rollbackToVersion(
  policyId: string,
  targetVersion: string,
  rollbackBy: string,
  reason: string,
): Promise<PolicyVersion> {
  // Get the target version
  const target = await getVersion(policyId, targetVersion);
  if (!target) {
    throw new Error(`Version "${targetVersion}" not found for policy "${policyId}"`);
  }

  // Create a new version with the target's content
  const rollbackDocument: PolicyDocument = {
    ...target.document,
    metadata: {
      ...target.document.metadata,
      // Bump patch version for the rollback
      version: bumpPatchVersion(target.document.metadata.version),
      updatedAt: new Date().toISOString(),
    },
  };

  return createVersion({
    policyId,
    document: rollbackDocument,
    changeDescription: `Rollback to v${targetVersion}: ${reason}`,
    createdBy: rollbackBy,
  });
}

/**
 * Activate a specific version (set as active, supersede current).
 */
export async function activateVersion(
  policyId: string,
  version: string,
  activatedBy: string,
): Promise<PolicyVersion> {
  const policy = await db.declPolicy.findUnique({ where: { policyId } });
  if (!policy) throw new Error(`Policy "${policyId}" not found`);

  const targetVersion = await db.declPolicyVersion.findUnique({
    where: { declPolicyId_version: { declPolicyId: policy.id, version } },
  });
  if (!targetVersion) throw new Error(`Version "${version}" not found`);

  // Supersede current active
  await db.declPolicyVersion.updateMany({
    where: { declPolicyId: policy.id, status: "active" },
    data: { status: "superseded" as PolicyVersionStatus },
  });

  // Activate target
  await db.declPolicyVersion.update({
    where: { id: targetVersion.id },
    data: { status: "active" as PolicyVersionStatus },
  });

  const document = JSON.parse(targetVersion.document) as PolicyDocument;

  // Update policy record
  await db.declPolicy.update({
    where: { policyId },
    data: {
      version: targetVersion.version,
      statements: targetVersion.document, // Already has full doc
      contentHash: targetVersion.contentHash,
      updatedAt: new Date(),
    },
  });

  return mapDbVersionToModel(targetVersion, document);
}

// ─── Helpers ──────────────────────────────────────────────────────────

function mapDbVersionToModel(
  v: { id: string; declPolicyId: string; version: string; contentHash: string; document: string; status: string; createdBy: string; changeDescription: string; parentVersionId: string | null; createdAt: Date },
  document: PolicyDocument,
): PolicyVersion {
  return {
    id: v.id,
    policyId: "", // Will be filled by caller if needed
    version: v.version,
    contentHash: v.contentHash,
    document,
    status: v.status as PolicyVersionStatus,
    createdBy: v.createdBy,
    createdAt: v.createdAt.toISOString(),
    changeDescription: v.changeDescription,
    parentVersionId: v.parentVersionId ?? undefined,
  };
}

function bumpPatchVersion(semver: string): string {
  const match = semver.match(/^(\d+)\.(\d+)\.(\d+)/);
  if (!match) return `${semver}-rollback`;
  const [, major, minor, patch] = match;
  return `${major}.${minor}.${Number(patch) + 1}`;
}
