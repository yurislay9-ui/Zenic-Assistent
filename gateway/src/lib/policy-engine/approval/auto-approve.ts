 * Cancel an approval request.
 * Can cancel from draft, pending_review, or approved states.
 */
export async function cancelApproval(
  approvalId: string,
  cancelledBy: string,
): Promise<PolicyApprovalRequest> {
  // Load current request
  const record = await db.policyApproval.findUnique({
    where: { approvalId },
  });
  if (!record) {
    throw new Error(`Approval request "${approvalId}" not found`);
  }

  // Validate state transition
  validateTransition(record.status, ApprovalStatusEnum.CANCELLED);

  // Add a cancellation note to approvals
  const existingApprovals = JSON.parse(record.approvals) as ApprovalDecision[];
  const cancellationDecision: ApprovalDecision = {
    reviewerId: cancelledBy,
    reviewerName: cancelledBy,
    decision: "rejected",
    role: "requester",
    comment: "Request cancelled by requester",
    decidedAt: new Date().toISOString(),
  };

  // Update the record
  const updated = await db.policyApproval.update({
    where: { approvalId },
    data: {
      status: ApprovalStatusEnum.CANCELLED,
      approvals: JSON.stringify([...existingApprovals, cancellationDecision]),
      updatedAt: new Date(),
    },
  });

  return mapDbToApprovalRequest(updated);
}

/**
 * Rollback a deployed approval to the previous version.
 *
 * - Only if status is "deployed"
 * - Use versioning.ts rollbackToVersion
 * - Set status to "rolled_back"
 */
export async function rollbackApproval(
  approvalId: string,
): Promise<PolicyApprovalRequest> {
  // Load current request
  const record = await db.policyApproval.findUnique({
    where: { approvalId },
  });
  if (!record) {
    throw new Error(`Approval request "${approvalId}" not found`);
  }

  // Validate state transition
  validateTransition(record.status, ApprovalStatusEnum.ROLLED_BACK);

  // Determine the previous version to rollback to
  const previousVersion = record.previousVersion;
  const policyId = record.targetPolicyId;

  if (!policyId) {
    throw new Error(
      `Cannot rollback approval "${approvalId}": no targetPolicyId associated with this request.`
    );
  }

  if (previousVersion) {
    // Rollback to specific previous version using versioning.ts
    await rollbackToVersion(
      policyId,
      previousVersion,
      record.requestedBy,
      `Rollback via approval workflow: ${record.title}`,
    );
  } else {
    // No explicit previous version — find the previous version in the version chain
    const policy = await db.declPolicy.findUnique({
      where: { policyId },
    });
    if (!policy) {
      throw new Error(`Policy "${policyId}" not found for rollback`);
    }

    // Find the most recent superseded version (the one before current)
    const supersededVersion = await db.declPolicyVersion.findFirst({
      where: { declPolicyId: policy.id, status: "superseded" },
      orderBy: { createdAt: "desc" },
    });

    if (supersededVersion) {
      const supersededDoc = JSON.parse(supersededVersion.document) as PolicyDocument;
      await rollbackToVersion(
        policyId,
        supersededVersion.version,
        record.requestedBy,
        `Rollback via approval workflow (auto-detected previous version): ${record.title}`,
      );
    } else {
      throw new Error(
        `Cannot rollback approval "${approvalId}": no previous version found for policy "${policyId}".`
      );
    }
  }

  // Update the approval record
  const updated = await db.policyApproval.update({
    where: { approvalId },
    data: {
      status: ApprovalStatusEnum.ROLLED_BACK,
      updatedAt: new Date(),
    },
  });

  return mapDbToApprovalRequest(updated);
}

/**
 * Find and expire approval requests past their expiry date.
 * Sets status to "expired" for all expired requests that are still in reviewable states.
 * Returns the number of expired requests.
 */
export async function checkExpiredApprovals(): Promise<number> {
  const now = new Date();

  // Find all requests that are past expiry and in an expirable state
  const expiredRequests = await db.policyApproval.findMany({
    where: {
      status: { in: [ApprovalStatusEnum.DRAFT, ApprovalStatusEnum.PENDING_REVIEW] },
      expiresAt: { not: null, lt: now },
    },
  });

  if (expiredRequests.length === 0) return 0;

  // Update all expired requests
  const updatePromises = expiredRequests.map((req) =>
    db.policyApproval.update({
      where: { approvalId: req.approvalId },
      data: {
        status: ApprovalStatusEnum.EXPIRED,
        updatedAt: now,
      },
    })
  );

  await Promise.all(updatePromises);

  return expiredRequests.length;
}

/**
 * Load a single approval request by ID.
 */
export async function getApprovalRequest(
  approvalId: string,
): Promise<PolicyApprovalRequest | null> {
  const record = await db.policyApproval.findUnique({
    where: { approvalId },
  });

  if (!record) return null;

  return mapDbToApprovalRequest(record);
}

/**
 * List approval requests with filtering and pagination.
 */
export async function listApprovalRequests(
  options?: ApprovalListOptions,
): Promise<{ requests: PolicyApprovalRequest[]; total: number }> {
  const {
    status,
    priority,
    requestedBy,
    targetPolicyId,
    limit = 50,
    offset = 0,
  } = options ?? {};

  // Build where clause
  const where: Record<string, unknown> = {};

  if (status) {
    if (Array.isArray(status)) {
      where.status = { in: status };
    } else {
      where.status = status;
    }
  }

  if (priority) {
    if (Array.isArray(priority)) {
      where.priority = { in: priority };
    } else {
      where.priority = priority;
    }
  }

  if (requestedBy) {
    where.requestedBy = requestedBy;
  }

  if (targetPolicyId) {
    where.targetPolicyId = targetPolicyId;
  }

  const [records, total] = await Promise.all([
    db.policyApproval.findMany({
      where,
      orderBy: { createdAt: "desc" },
      take: limit,
      skip: offset,
    }),
    db.policyApproval.count({ where }),
  ]);

  const requests = records.map(mapDbToApprovalRequest);

  return { requests, total };
}

// ─── Validation Helpers ──────────────────────────────────────────────

/**
 * Validate a proposed policy document has all required fields.
 * @throws Error if the document is invalid
 */
function validateProposedDocument(document: PolicyDocument): void {
  if (!document.apiVersion) {
    throw new Error("Proposed document must have an apiVersion");
  }
  if (!document.kind) {
    throw new Error("Proposed document must have a kind");
  }
  if (!document.metadata?.id) {
    throw new Error("Proposed document must have metadata.id");
  }
  if (!document.metadata?.name) {
    throw new Error("Proposed document must have metadata.name");
  }
  if (!document.metadata?.version) {
    throw new Error("Proposed document must have metadata.version");
  }
  if (!document.metadata?.description) {
    throw new Error("Proposed document must have metadata.description");
  }
  if (!Array.isArray(document.statements)) {
    throw new Error("Proposed document must have a statements array");
  }
  // Validate each statement
  for (let i = 0; i < document.statements.length; i++) {
    const stmt = document.statements[i];
    if (!stmt.id) {
      throw new Error(`Statement at index ${i} must have an id`);
    }
    if (!stmt.effect) {
      throw new Error(`Statement "${stmt.id}" must have an effect`);
    }
    if (!stmt.resource) {
      throw new Error(`Statement "${stmt.id}" must have a resource`);
    }
    if (!stmt.action) {
      throw new Error(`Statement "${stmt.id}" must have an action`);
    }
  }
}
