  const sagaExecution = await db.sagaExecution.create({
    data: {
      executionId,
      sagaType,
      status: "running",
      tenantId,
      subscriptionId: subscriptionId || null,
      currentStepIndex: 0,
      totalSteps: steps.length,
      completedSteps: 0,
      metadata: JSON.stringify(input),
      startedAt: new Date(),
    },
  });

  // Persist step records
  const stepRecords: Array<{ id: string; stepIndex: number; stepName: string; action: string; compensatingAction: string; isCritical: boolean; status: string; output: Record<string, unknown>; error?: string }> = [];
  for (const step of steps) {
    const record = await db.sagaStepRecord.create({
      data: {
        sagaExecutionDbId: sagaExecution.id,
        stepIndex: step.step_index,
        stepName: step.step_name,
        action: step.action,
        compensatingAction: step.compensating_action,
        isCritical: step.is_critical,
        status: "pending",
        input: JSON.stringify(input),
        requiresExternalInput: step.requires_external_input,
      },
    });
    stepRecords.push({
      id: record.id,
      stepIndex: step.step_index,
      stepName: step.step_name,
      action: step.action,
      compensatingAction: step.compensating_action,
      isCritical: step.is_critical,
      status: "pending",
      output: {},
    });
  }

  // Execute steps sequentially
  let currentStatus: SagaStatusName = "running";
  let completedSteps = 0;
  const stepOutputs: Record<number, Record<string, unknown>> = {};

  for (let i = 0; i < steps.length; i++) {
    const step = steps[i];
    const stepRecord = stepRecords[i];

    // Update step to running
    await db.sagaStepRecord.update({
      where: { id: stepRecord.id },
      data: { status: "running", startedAt: new Date() },
    });

    // Find and execute the handler
    const handler = stepHandlers[step.action];
    if (!handler) {
      // No handler found — this is a configuration error
      await db.sagaStepRecord.update({
        where: { id: stepRecord.id },
        data: { status: "failed", errorMessage: `No handler for action: ${step.action}`, completedAt: new Date() },
      });
      stepRecords[i].status = "failed";
      stepRecords[i].error = `No handler for action: ${step.action}`;

      if (step.is_critical) {
        currentStatus = "compensating";
        break;
      }
      continue;
    }

    try {
      const stepInput = { ...input, ...stepOutputs[i - 1], tenantId };
      const result = await handler(stepInput);

      if (result.success) {
        stepOutputs[i] = result.output || {};
        stepRecords[i].status = "completed";
        stepRecords[i].output = result.output || {};
        completedSteps++;

        await db.sagaStepRecord.update({
          where: { id: stepRecord.id },
          data: { status: "completed", output: JSON.stringify(result.output || {}), completedAt: new Date() },
        });

        // Check if step requires external input (pauses saga)
        if (step.requires_external_input) {
          currentStatus = "paused";
          await db.sagaExecution.update({
            where: { id: sagaExecution.id },
            data: { status: "paused", currentStepIndex: i, completedSteps },
          });
          break;
        }
      } else {
        stepRecords[i].status = "failed";
        stepRecords[i].error = result.error || "Step failed";
        await db.sagaStepRecord.update({
          where: { id: stepRecord.id },
          data: { status: "failed", errorMessage: result.error || "Step failed", completedAt: new Date() },
        });

        if (step.is_critical) {
          currentStatus = "compensating";
          break;
        }
        // Non-critical failure — continue
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : String(err);
      stepRecords[i].status = "failed";
      stepRecords[i].error = errorMsg;
      await db.sagaStepRecord.update({
        where: { id: stepRecord.id },
        data: { status: "failed", errorMessage: errorMsg, completedAt: new Date() },
      });

      if (step.is_critical) {
        currentStatus = "compensating";
        break;
      }
    }
  }

  // Handle compensation if needed
  if (currentStatus === "compensating") {
    const failedStepIndex = stepRecords.findIndex(s => s.status === "failed");
    // Run compensating actions for all completed steps in reverse order
    for (let i = failedStepIndex - 1; i >= 0; i--) {
      const stepRecord = stepRecords[i];
      const step = steps[i];

      if (stepRecord.status !== "completed") continue;
      if (step.compensating_action === "none") continue;

      await db.sagaStepRecord.update({
        where: { id: stepRecord.id },
        data: { status: "compensating", compensationStartedAt: new Date() },
      });

      const compensationHandler = compensationHandlers[step.compensating_action];
      if (compensationHandler) {
        try {
          await compensationHandler(input, stepOutputs[i] || {});
          await db.sagaStepRecord.update({
            where: { id: stepRecord.id },
            data: { status: "compensated", compensationCompletedAt: new Date() },
          });
          stepRecords[i].status = "compensated";
        } catch {
          await db.sagaStepRecord.update({
            where: { id: stepRecord.id },
            data: { status: "failed", compensationError: "Compensation failed", compensationCompletedAt: new Date() },
          });
          currentStatus = "failed";
        }
      } else {
        // No compensation handler — use step handler approach
        const compensatingAction = stepHandlers[step.compensating_action];
        if (compensatingAction) {
          try {
            await compensatingAction({ ...input, ...stepOutputs[i], tenantId });
            await db.sagaStepRecord.update({
              where: { id: stepRecord.id },
              data: { status: "compensated", compensationCompletedAt: new Date() },
            });
            stepRecords[i].status = "compensated";
          } catch {
            await db.sagaStepRecord.update({
              where: { id: stepRecord.id },
              data: { status: "failed", compensationError: "Compensation handler failed", compensationCompletedAt: new Date() },
            });
            currentStatus = "failed";
          }
        } else {
          // No compensation handler available — mark as compensated (best-effort)
          await db.sagaStepRecord.update({
            where: { id: stepRecord.id },
            data: { status: "compensated", compensationCompletedAt: new Date() },
          });
          stepRecords[i].status = "compensated";
        }
      }
    }

    if (currentStatus === "compensating") {
      currentStatus = "compensated";
    }
  } else if (currentStatus === "running" || currentStatus === "paused") {
    // All steps completed or paused
    if (completedSteps === steps.length || currentStatus === "paused") {
      // Will be set properly below
    }
  }

  // Determine final status
  if (currentStatus !== "failed" && currentStatus !== "paused") {
    if (completedSteps === steps.length) {
      currentStatus = "completed";
    } else if (currentStatus === "compensated") {
      // Already set
    }
  }

  // Update saga execution
  await db.sagaExecution.update({
    where: { id: sagaExecution.id },
    data: {
      status: currentStatus,
      currentStepIndex: stepRecords.findIndex(s => s.status === "failed" || s.status === "paused"),
      completedSteps,
      completedAt: currentStatus === "completed" || currentStatus === "compensated" || currentStatus === "failed" ? new Date() : null,
      errorMessage: stepRecords.find(s => s.status === "failed")?.error,
      compensationReason: currentStatus === "compensated" || currentStatus === "compensating"
        ? stepRecords.find(s => s.status === "failed")?.error : null,
      updatedAt: new Date(),
    },
  });

  return {
    executionId,
    sagaType,
    status: currentStatus,
    currentStepIndex: stepRecords.findIndex(s => s.status === "failed" || s.status === "paused"),
    totalSteps: steps.length,
    completedSteps,
    errorMessage: stepRecords.find(s => s.status === "failed")?.error,
    compensationReason: currentStatus === "compensated" ? stepRecords.find(s => s.status === "failed")?.error : undefined,
    steps: stepRecords.map(s => ({
      stepIndex: s.stepIndex,
      stepName: s.stepName,
      status: s.status as SagaStepStatusName,
      output: s.output,
      error: s.error,
    })),
  };
}

/**
 * Resume a paused Saga (after external input like admin confirmation)
 */
export async function resumeSaga(
  executionId: string,
  resumeInput: Record<string, unknown>,
): Promise<SagaOrchestratorResult> {
  const sagaExecution = await db.sagaExecution.findUnique({
    where: { executionId },
    include: { steps: { orderBy: { stepIndex: "asc" } } },
  });

  // BUG #10 FIX: Don't access sagaExecution after null check
  if (!sagaExecution) {
    return {
      executionId,
      sagaType: "trial_creation" as SagaTypeName, // Safe default, not null dereference
      status: "failed",
      currentStepIndex: 0,
      totalSteps: 0,
      completedSteps: 0,
      errorMessage: `Saga execution not found: ${executionId}`,
      steps: [],
    };
  }

  if (sagaExecution.status !== "paused") {
    return {
      executionId,
      sagaType: sagaExecution.sagaType as SagaTypeName,
      status: sagaExecution.status as SagaStatusName,
      currentStepIndex: sagaExecution.currentStepIndex,
      totalSteps: sagaExecution.totalSteps,
      completedSteps: sagaExecution.completedSteps,
      errorMessage: "Saga is not paused — cannot resume",
      steps: [],
    };
  }

  // Parse original input
  const originalInput = JSON.parse(sagaExecution.metadata || "{}");
  const input = { ...originalInput, ...resumeInput, tenantId: sagaExecution.tenantId };

  // Find the step that caused the pause (requires_external_input)
  const pausedStepIndex = sagaExecution.steps.findIndex(s => s.requiresExternalInput && s.status === "completed");

  // The step AFTER the paused step needs to continue
  // For payment sagas, the next step after await_admin_confirmation is finalize_payment_confirmation
  const nextStepIndex = pausedStepIndex + 1;
  if (nextStepIndex >= sagaExecution.totalSteps) {
    // All steps done — mark as completed
    await db.sagaExecution.update({
      where: { id: sagaExecution.id },
      data: { status: "completed", completedAt: new Date(), updatedAt: new Date() },
    });
    return {
      executionId,
      sagaType: sagaExecution.sagaType as SagaTypeName,
      status: "completed",
      currentStepIndex: sagaExecution.currentStepIndex,
      totalSteps: sagaExecution.totalSteps,
      completedSteps: sagaExecution.totalSteps,
      steps: [],
    };
  }

  // Execute remaining steps
  await db.sagaExecution.update({
    where: { id: sagaExecution.id },
    data: { status: "running", updatedAt: new Date() },
  });

  let currentStatus: SagaStatusName = "running";
  let completedSteps = sagaExecution.completedSteps;
  const stepOutputs: Record<number, Record<string, unknown>> = {};

  // Get step definitions
  const { getSagaDefinition } = await import("./wasm-bridge");
  const definition = getSagaDefinition(sagaExecution.sagaType as SagaTypeName);
  if (!definition?.steps) {
    return {
      executionId,
      sagaType: sagaExecution.sagaType as SagaTypeName,
      status: "failed",
      currentStepIndex: sagaExecution.currentStepIndex,
      totalSteps: sagaExecution.totalSteps,
      completedSteps,
      errorMessage: "Could not load saga definition for resume",
      steps: [],
    };
  }

  const steps = definition.steps;

  for (let i = nextStepIndex; i < steps.length; i++) {
    const step = steps[i];
    const stepRecord = sagaExecution.steps[i];

    await db.sagaStepRecord.update({
      where: { id: stepRecord.id },
      data: { status: "running", startedAt: new Date() },
    });

    const handler = stepHandlers[step.action];
    if (!handler) {
      await db.sagaStepRecord.update({
