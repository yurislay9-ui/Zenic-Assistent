  for (const param of template.parameters) {
    if (param.name in request.parameters && request.parameters[param.name] !== undefined && request.parameters[param.name] !== null) {
      // Provided value
      resolvedParams[param.name] = request.parameters[param.name];
    } else if (param.defaultValue !== undefined) {
      // Default value from template definition
      resolvedParams[param.name] = param.defaultValue;
      warnings.push(`Parameter "${param.name}" using default value: ${JSON.stringify(param.defaultValue)}`);
    } else if (template.defaults[param.name] !== undefined) {
      // Default value from defaults map
      resolvedParams[param.name] = template.defaults[param.name];
      warnings.push(`Parameter "${param.name}" using default from defaults map: ${JSON.stringify(template.defaults[param.name])}`);
    } else if (param.required) {
      // Required but no value — error
      unresolvedParameters.push(param.name);
      errors.push(`Required parameter "${param.name}" has no value`);
    }
    // Optional parameter with no value → skip (unresolved)
  }

  // Early return if required parameters are missing
  if (errors.length > 0) {
    return {
      success: false,
      errors,
      warnings,
      unresolvedParameters,
    };
  }

  // 4. Apply parameter type validation
  for (const param of template.parameters) {
    if (param.name in resolvedParams) {
      const result = validateParameterType(resolvedParams[param.name], param);
      if (!result.valid) {
        errors.push(result.error!);
      }
    }
  }

  if (errors.length > 0) {
    return {
      success: false,
      errors,
      warnings,
      unresolvedParameters,
    };
  }

  // 5. Validate constraint rules
  const constraintResult = validateConstraints(template.constraints, resolvedParams);
  if (!constraintResult.valid) {
    errors.push(...constraintResult.errors);
  }

  if (errors.length > 0) {
    return {
      success: false,
      errors,
      warnings,
      unresolvedParameters,
    };
  }

  // 6 & 7. Build PolicyDocument via Builder with variable substitution
  const builder = new PolicyDocumentBuilder(
    template.documentTemplate,
    resolvedParams,
    template.metadata,
  );
  const document = builder.build();

  // Verify no critical unresolved variables in generated document
  const docString = JSON.stringify(document);
  const remainingVars = hasUnresolvedVariables(docString);
  if (remainingVars.length > 0) {
    const uniqueVars = [...new Set(remainingVars)];
    warnings.push(`Unresolved variables remain in generated document: ${uniqueVars.join(", ")}`);
  }

  // 8. Auto-deploy if requested
  let policyId: string | undefined;
  if (request.autoDeploy) {
    try {
      const targetId = request.targetPolicyId ?? `${template.metadata.id}-${Date.now()}`;
      const contentHash = computeContentHash(document);

      // Check if policy already exists
      const existing = await db.declPolicy.findUnique({
        where: { policyId: targetId },
      });

      if (existing) {
        // Update existing policy
        await db.declPolicy.update({
          where: { policyId: targetId },
          data: {
            name: document.metadata.name,
            description: document.metadata.description,
            version: document.metadata.version,
            labels: JSON.stringify(document.metadata.labels ?? {}),
            compliance: JSON.stringify(document.metadata.compliance ?? []),
            statements: JSON.stringify(document.statements),
            tests: JSON.stringify(document.tests ?? []),
            contentHash,
            author: request.requestedBy,
          },
        });
        policyId = targetId;
      } else {
        // Create new policy
        await db.declPolicy.create({
          data: {
            policyId: targetId,
            name: document.metadata.name,
            description: document.metadata.description,
            apiVersion: POLICY_API_VERSION,
            version: document.metadata.version,
            labels: JSON.stringify(document.metadata.labels ?? {}),
            compliance: JSON.stringify(document.metadata.compliance ?? []),
            statements: JSON.stringify(document.statements),
            tests: JSON.stringify(document.tests ?? []),
            isActive: true,
            contentHash,
            author: request.requestedBy,
          },
        });
        policyId = targetId;
      }
    } catch (error) {
      errors.push(`Auto-deploy failed: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  // 9. Increment template's generatedCount
  try {
    await db.policyTemplate.update({
      where: { templateId: request.templateId },
      data: {
        generatedCount: { increment: 1 },
      },
    });
  } catch (error) {
    warnings.push(`Failed to increment generatedCount: ${error instanceof Error ? error.message : String(error)}`);
  }

  // 10. Return result
  return {
    success: errors.length === 0,
    document: errors.length === 0 ? document : undefined,
    errors,
    warnings,
    policyId,
    unresolvedParameters: [],
  };
}

/**
 * Update a template by templateId.
 * Only the provided fields will be updated.
 * Recomputes content hash if any content fields change.
 */
export async function updateTemplate(
  templateId: string,
  updates: Partial<PolicyTemplate>,
): Promise<TemplateDbRecord> {
  // 1. Verify template exists
  const existing = await db.policyTemplate.findUnique({
    where: { templateId },
  });

  if (!existing) {
    throw new TemplateValidationError(
      `Template "${templateId}" not found`,
      "templateId",
      templateId,
    );
  }

  // 2. Build update data
  const data: Record<string, unknown> = {};

  if (updates.metadata) {
    if (updates.metadata.name !== undefined) data.name = updates.metadata.name;
    if (updates.metadata.version !== undefined) data.version = updates.metadata.version;
    if (updates.metadata.description !== undefined) data.description = updates.metadata.description;
    if (updates.metadata.category !== undefined) data.category = updates.metadata.category;
    if (updates.metadata.industry !== undefined) data.industry = updates.metadata.industry;
    if (updates.metadata.tags !== undefined) data.tags = JSON.stringify(updates.metadata.tags);
    if (updates.metadata.author !== undefined) data.author = updates.metadata.author;
  }

  if (updates.parameters !== undefined) {
    // Validate parameter definitions if updating
    const paramNames = new Set<string>();
    for (const param of updates.parameters) {
      if (paramNames.has(param.name)) {
        throw new TemplateValidationError(
          `Duplicate parameter name "${param.name}" in update`,
          "parameters",
        );
      }
      paramNames.add(param.name);
      if (param.type && !VALID_PARAMETER_TYPES.has(param.type)) {
        throw new TemplateValidationError(
          `Invalid parameter type "${param.type}"`,
          `parameters.${param.name}.type`,
          param.type,
        );
      }
    }
    data.parameters = JSON.stringify(updates.parameters);
  }

  if (updates.documentTemplate !== undefined) {
    // Validate document template if updating
    if (!Array.isArray(updates.documentTemplate.statements) || updates.documentTemplate.statements.length === 0) {
      throw new TemplateValidationError(
        "documentTemplate.statements must be a non-empty array",
        "documentTemplate.statements",
      );
    }
    data.documentTemplate = JSON.stringify(updates.documentTemplate);
  }

  if (updates.defaults !== undefined) {
    data.defaults = JSON.stringify(updates.defaults);
  }

  if (updates.constraints !== undefined) {
    // Validate constraints if updating
    for (const constraint of updates.constraints) {
      if (constraint.type && !VALID_CONSTRAINT_TYPES.has(constraint.type)) {
        throw new TemplateValidationError(
          `Invalid constraint type "${constraint.type}"`,
          `constraints.${constraint.name}.type`,
          constraint.type,
        );
      }
    }
    data.constraints = JSON.stringify(updates.constraints);
  }

  // 3. Recompute content hash if any content fields changed
  const contentFieldsChanged = ["parameters", "documentTemplate", "defaults", "constraints", "name", "description", "category", "industry"].some(
    (field) => field in data,
  );

  if (contentFieldsChanged) {
    // Reconstruct the full template with updates for hash computation
    const existingRecord = mapDbToRecord(existing);
    const existingTemplate = dbRecordToTemplate(existingRecord);
    const mergedTemplate: PolicyTemplate = {
      ...existingTemplate,
      ...updates,
      metadata: {
        ...existingTemplate.metadata,
        ...(updates.metadata ?? {}),
      },
    };
    data.contentHash = computeTemplateContentHash(mergedTemplate);
  }

  // 4. Persist update
  try {
    const updated = await db.policyTemplate.update({
      where: { templateId },
      data,
    });

    return mapDbToRecord(updated);
  } catch (error) {
    throw new TemplateValidationError(
      `Failed to update template "${templateId}": ${error instanceof Error ? error.message : String(error)}`,
      "templateId",
      templateId,
    );
  }
}

/**
 * Delete (deactivate) a template by templateId.
 * Soft delete — sets isActive to false instead of removing the record.
 */
export async function deleteTemplate(
  templateId: string,
): Promise<TemplateDbRecord> {
  // 1. Verify template exists
  const existing = await db.policyTemplate.findUnique({
    where: { templateId },
  });

  if (!existing) {
    throw new TemplateValidationError(
      `Template "${templateId}" not found`,
      "templateId",
      templateId,
    );
  }

  // 2. Soft delete (deactivate)
  try {
    const deactivated = await db.policyTemplate.update({
      where: { templateId },
      data: { isActive: false },
    });

    return mapDbToRecord(deactivated);
  } catch (error) {
    throw new TemplateValidationError(
      `Failed to deactivate template "${templateId}": ${error instanceof Error ? error.message : String(error)}`,
      "templateId",
      templateId,
    );
  }
}
