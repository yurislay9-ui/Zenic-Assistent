      targetPolicyId: targetPolicyId ?? null,
      previousVersion: previousVersion ?? null,
      proposedDocument: JSON.stringify(proposedDocument),
      simulationId: simulationId ?? null,
      requestedBy,
      requiredApprovals,
      currentApprovals: 0,
      approvals: "[]",
      requiredReviewerRoles: JSON.stringify(reviewerRoles),
      autoApproveRules: JSON.stringify(rules),
      autoApproved: false,
      expiresAt,
      deployedAt: null,
    },
  });

  return mapDbToApprovalRequest(record);
}

/**
 * Submit an approval request for review.
 * Moves from "draft" to "pending_review".
 * If auto-approve rules match → auto-approve immediately.
 */
export async function submitForReview(
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
  validateTransition(record.status, ApprovalStatusEnum.PENDING_REVIEW);

  // Validate required fields for submission
  if (!record.title || !record.proposedDocument || !record.requestedBy) {
    throw new Error("Cannot submit for review: missing required fields (title, proposedDocument, requestedBy)");
  }

  // Check auto-approve rules
  const proposedDocument = JSON.parse(record.proposedDocument) as PolicyDocument;
  const existingDocument = await loadExistingDocument(record.targetPolicyId);
  const autoApproveRules = JSON.parse(record.autoApproveRules) as AutoApproveRule[];

  const shouldAutoApprove = evaluateAutoApproveRules(autoApproveRules, proposedDocument, existingDocument);

  const newStatus = shouldAutoApprove
    ? ApprovalStatusEnum.APPROVED
    : ApprovalStatusEnum.PENDING_REVIEW;

  // Update the record
  const updated = await db.policyApproval.update({
    where: { approvalId },
    data: {
      status: newStatus,
      autoApproved: shouldAutoApprove,
      currentApprovals: shouldAutoApprove
        ? record.requiredApprovals
        : record.currentApprovals,
      updatedAt: new Date(),
    },
  });

  return mapDbToApprovalRequest(updated);
}

/**
 * Add an approval or rejection decision to an approval request.
 * Command pattern: ApprovalDecision is the command object.
 *
 * - If rejection → set status to "rejected"
 * - If approval → increment currentApprovals
 * - If currentApprovals >= requiredApprovals → set status to "approved"
 * - Validate reviewer has required role
 */
export async function approveRequest(
  approvalId: string,
  decision: ApprovalDecision,
): Promise<PolicyApprovalRequest> {
  // Load current request
  const record = await db.policyApproval.findUnique({
    where: { approvalId },
  });
  if (!record) {
    throw new Error(`Approval request "${approvalId}" not found`);
  }

  // Only pending_review requests can receive decisions
  if (record.status !== ApprovalStatusEnum.PENDING_REVIEW) {
    throw new Error(
      `Cannot add decision to approval request in "${record.status}" status. ` +
      `Expected "${ApprovalStatusEnum.PENDING_REVIEW}".`
    );
  }

  // Validate reviewer has a required role
  const requiredRoles = JSON.parse(record.requiredReviewerRoles) as string[];
  if (requiredRoles.length > 0 && !requiredRoles.includes(decision.role)) {
    throw new Error(
      `Reviewer role "${decision.role}" is not authorized. ` +
      `Required roles: [${requiredRoles.join(", ")}]`
    );
  }

  // Check for duplicate reviewer
  const existingApprovals = JSON.parse(record.approvals) as ApprovalDecision[];
  const alreadyReviewed = existingApprovals.some((a) => a.reviewerId === decision.reviewerId);
  if (alreadyReviewed) {
    throw new Error(
      `Reviewer "${decision.reviewerId}" has already submitted a decision on this request.`
    );
  }

  // Apply the decision (Command pattern)
  const updatedApprovals = [...existingApprovals, decision];
  let newStatus: string = record.status;
  let newCurrentApprovals = record.currentApprovals;

  if (decision.decision === "rejected") {
    // Rejection → set status to "rejected"
    validateTransition(record.status, ApprovalStatusEnum.REJECTED);
    newStatus = ApprovalStatusEnum.REJECTED;
  } else {
    // Approval → increment currentApprovals
    // BUG #12 FIX: Atomic increment inside transaction to prevent race condition
    // where two concurrent reviewers both read the same count and both increment by 1
    // but one increment is lost.
    newCurrentApprovals = record.currentApprovals + 1;
    if (newCurrentApprovals >= record.requiredApprovals) {
      // Enough approvals → set status to "approved"
      validateTransition(record.status, ApprovalStatusEnum.APPROVED);
      newStatus = ApprovalStatusEnum.APPROVED;
    }
  }

  // BUG #12 FIX: Use $transaction to ensure atomic read-modify-write
  const updated = await db.$transaction(async (tx) => {
    // Re-read inside transaction to get the latest state
    const freshRecord = await tx.policyApproval.findUnique({
      where: { approvalId },
    });
    if (!freshRecord) {
      throw new Error(`Approval request "${approvalId}" not found during transaction`);
    }

    // Re-validate: still in pending_review?
    if (freshRecord.status !== ApprovalStatusEnum.PENDING_REVIEW) {
      throw new Error(
        `Approval request "${approvalId}" status changed to "${freshRecord.status}" during review. Please retry.`
      );
    }

    // Merge approvals from concurrent reviewers
    const freshApprovals = JSON.parse(freshRecord.approvals) as ApprovalDecision[];
    const mergedApprovals = [...freshApprovals, decision];

    let finalStatus = freshRecord.status;
    let finalCurrentApprovals = freshRecord.currentApprovals;

    if (decision.decision === "rejected") {
      finalStatus = ApprovalStatusEnum.REJECTED;
    } else {
      finalCurrentApprovals = freshRecord.currentApprovals + 1;
      if (finalCurrentApprovals >= freshRecord.requiredApprovals) {
        finalStatus = ApprovalStatusEnum.APPROVED;
      }
    }

    return tx.policyApproval.update({
      where: { approvalId },
      data: {
        status: finalStatus,
        currentApprovals: finalCurrentApprovals,
        approvals: JSON.stringify(mergedApprovals),
        updatedAt: new Date(),
      },
    });
  });

  return mapDbToApprovalRequest(updated);
}

/**
 * Deploy an approved policy change.
 *
 * - Only if status is "approved"
 * - Use versioning.ts createVersion to create a new version
 * - Update DeclPolicy with new content
 * - Set status to "deployed"
 * - Record deployment timestamp
 */
export async function deployApproval(
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
  validateTransition(record.status, ApprovalStatusEnum.DEPLOYED);

  const proposedDocument = JSON.parse(record.proposedDocument) as PolicyDocument;
  const policyId = record.targetPolicyId ?? proposedDocument.metadata.id;

  // Use versioning.ts createVersion to create a new version
  await createVersion({
    policyId,
    document: proposedDocument,
    changeDescription: record.description,
    createdBy: record.requestedBy,
  });

  // Update DeclPolicy with new content (createVersion already does this,
  // but we also update the contentHash explicitly)
  const newContentHash = computeContentHash(proposedDocument);
  await db.declPolicy.update({
    where: { policyId },
    data: {
      contentHash: newContentHash,
      version: proposedDocument.metadata.version,
      statements: JSON.stringify(proposedDocument.statements),
      tests: JSON.stringify(proposedDocument.tests ?? []),
      labels: JSON.stringify(proposedDocument.metadata.labels ?? {}),
      compliance: JSON.stringify(proposedDocument.metadata.compliance ?? []),
      updatedAt: new Date(),
    },
  });

  // Update the approval record
  const updated = await db.policyApproval.update({
    where: { approvalId },
    data: {
      status: ApprovalStatusEnum.DEPLOYED,
      deployedAt: new Date(),
      updatedAt: new Date(),
    },
  });

  return mapDbToApprovalRequest(updated);
}

/**
