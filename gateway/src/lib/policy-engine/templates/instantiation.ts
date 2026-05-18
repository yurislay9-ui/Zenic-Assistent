  if (!template.metadata) {
    errors.push("metadata is required");
  } else {
    if (!template.metadata.id || typeof template.metadata.id !== "string") {
      errors.push("metadata.id is required and must be a string");
    }
    if (!template.metadata.name || typeof template.metadata.name !== "string") {
      errors.push("metadata.name is required and must be a string");
    }
    if (!template.metadata.version || typeof template.metadata.version !== "string") {
      errors.push("metadata.version is required and must be a string");
    }
    if (!template.metadata.description || typeof template.metadata.description !== "string") {
      errors.push("metadata.description is required and must be a string");
    }
    if (!template.metadata.category || typeof template.metadata.category !== "string") {
      errors.push("metadata.category is required and must be a string");
    }
    // Validate semver
    if (template.metadata.version && !/^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$/.test(template.metadata.version)) {
      errors.push(`Invalid semver format: "${template.metadata.version}"`);
    }
  }

  // parameters
  if (!Array.isArray(template.parameters)) {
    errors.push("parameters must be an array");
  } else {
    const paramNames = new Set<string>();
    for (let i = 0; i < template.parameters.length; i++) {
      const param = template.parameters[i]!;
      const prefix = `parameters[${i}]`;

      if (!param.name || typeof param.name !== "string") {
        errors.push(`${prefix}.name is required and must be a string`);
      } else {
        if (paramNames.has(param.name)) {
          errors.push(`${prefix}.name "${param.name}" is duplicated — parameter names must be unique`);
        }
        paramNames.add(param.name);
      }

      if (!param.displayName || typeof param.displayName !== "string") {
        errors.push(`${prefix}.displayName is required`);
      }

      if (!param.description || typeof param.description !== "string") {
        errors.push(`${prefix}.description is required`);
      }

      if (!param.type || !VALID_PARAMETER_TYPES.has(param.type)) {
        errors.push(`${prefix}.type must be one of: ${[...VALID_PARAMETER_TYPES].join(", ")}`);
      }

      if (param.type === TemplateParameterType.ENUM && (!param.allowedValues || param.allowedValues.length === 0)) {
        errors.push(`${prefix}.allowedValues is required for ENUM type parameter "${param.name}"`);
      }

      if (typeof param.required !== "boolean") {
        errors.push(`${prefix}.required must be a boolean`);
      }
    }
  }

  // documentTemplate
  if (!template.documentTemplate) {
    errors.push("documentTemplate is required");
  } else {
    const doc = template.documentTemplate;
    if (!doc.name || typeof doc.name !== "string") {
      errors.push("documentTemplate.name is required and must be a string");
    }
    if (!doc.description || typeof doc.description !== "string") {
      errors.push("documentTemplate.description is required and must be a string");
    }
    if (!Array.isArray(doc.statements) || doc.statements.length === 0) {
      errors.push("documentTemplate.statements must be a non-empty array");
    } else {
      for (let i = 0; i < doc.statements.length; i++) {
        const stmt = doc.statements[i]!;
        const prefix = `documentTemplate.statements[${i}]`;

        if (!stmt.id || typeof stmt.id !== "string") {
          errors.push(`${prefix}.id is required`);
        }
        if (!stmt.effect || !VALID_EFFECTS.has(stmt.effect)) {
          errors.push(`${prefix}.effect must be one of: ${[...VALID_EFFECTS].join(", ")}`);
        }
        if (!stmt.resource || typeof stmt.resource !== "string") {
          errors.push(`${prefix}.resource is required`);
        }
        if (!stmt.action || typeof stmt.action !== "string") {
          errors.push(`${prefix}.action is required`);
        }
      }
    }
  }

  // constraints (optional)
  if (template.constraints && Array.isArray(template.constraints)) {
    for (let i = 0; i < template.constraints.length; i++) {
      const constraint = template.constraints[i]!;
      const prefix = `constraints[${i}]`;

      if (!constraint.name || typeof constraint.name !== "string") {
        errors.push(`${prefix}.name is required`);
      }
      if (!constraint.type || !VALID_CONSTRAINT_TYPES.has(constraint.type)) {
        errors.push(`${prefix}.type must be one of: ${[...VALID_CONSTRAINT_TYPES].join(", ")}`);
      }
      if (!constraint.parameters || typeof constraint.parameters !== "object") {
        errors.push(`${prefix}.parameters is required and must be an object`);
      }
      if (!constraint.errorMessage || typeof constraint.errorMessage !== "string") {
        errors.push(`${prefix}.errorMessage is required`);
      }
    }
  }

  return errors;
}

/**
 * Compute a SHA-256 content hash for a PolicyTemplate.
 * Uses canonical JSON serialization for deterministic hashing.
 */
function computeTemplateContentHash(template: PolicyTemplate): string {
  const canonical = JSON.stringify(template, Object.keys(template).sort(), 2);
  return createHash("sha256").update(canonical).digest("hex");
}

// ─── Policy Document Builder ──────────────────────────────────────────

/**
 * Builder for constructing a PolicyDocument from a template and resolved parameters.
 * Applies variable substitution across all template fields using the Interpreter pattern.
 */
class PolicyDocumentBuilder {
  private documentTemplate: PolicyDocumentTemplate;
  private resolvedParams: Record<string, unknown>;
  private templateMetadata: TemplateMetadata;

  constructor(
    documentTemplate: PolicyDocumentTemplate,
    resolvedParams: Record<string, unknown>,
    templateMetadata: TemplateMetadata,
  ) {
    this.documentTemplate = documentTemplate;
    this.resolvedParams = resolvedParams;
    this.templateMetadata = templateMetadata;
  }

  /**
   * Build a complete PolicyDocument from the template.
   */
  build(): PolicyDocument {
    // Substitute metadata
    const policyName = substituteVariables(this.documentTemplate.name, this.resolvedParams);
    const policyDescription = substituteVariables(this.documentTemplate.description, this.resolvedParams);

    // Build statements
    const statements = this.documentTemplate.statements.map((stmt) =>
      this.buildStatement(stmt),
    );

    // Build tests (optional)
    const tests = this.documentTemplate.tests
      ? this.documentTemplate.tests.map((tc) => this.buildTestCase(tc))
      : undefined;

    // Build compliance (substitute in standard names if needed)
    const compliance = this.documentTemplate.compliance
      ? substituteDeep(this.documentTemplate.compliance, this.resolvedParams)
      : undefined;

    // Build labels
    const labels = this.documentTemplate.labels
      ? substituteDeep(this.documentTemplate.labels, this.resolvedParams)
      : undefined;

    return {
      apiVersion: POLICY_API_VERSION,
      kind: POLICY_KIND,
      metadata: {
        id: this.templateMetadata.id,
        name: policyName,
        version: this.templateMetadata.version,
        description: policyDescription,
        compliance,
        labels,
        author: this.templateMetadata.author,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      },
      statements,
      tests,
    };
  }

  /**
   * Build a single PolicyStatement from a StatementTemplate.
   */
  private buildStatement(template: StatementTemplate): PolicyStatement {
    const id = substituteVariables(template.id, this.resolvedParams);
    const effect = substituteVariables(template.effect, this.resolvedParams) as PolicyEffectV2;
    const resource = substituteVariables(template.resource, this.resolvedParams);
    const action = substituteVariables(template.action, this.resolvedParams);
    const description = template.description
      ? substituteVariables(template.description, this.resolvedParams)
      : undefined;
    const requiredRole = template.requiredRole
      ? substituteVariables(template.requiredRole, this.resolvedParams)
      : undefined;
    const tags = template.tags
      ? template.tags.map((t) => substituteVariables(t, this.resolvedParams))
      : undefined;

    // Resolve priority — can be a number or a string template
    let priority: number;
    if (typeof template.priority === "number") {
      priority = template.priority;
    } else {
      const resolved = substituteVariables(template.priority, this.resolvedParams);
      const parsed = parseInt(resolved, 10);
      priority = isNaN(parsed) ? 0 : parsed;
    }

    // Build conditions
    const conditions = template.conditions
      ? template.conditions.map((ct) => this.buildCondition(ct))
      : undefined;

    return {
      id,
      effect,
      resource,
      action,
      conditions,
      priority,
      description,
      requiredRole,
      tags,
    };
  }

  /**
   * Build a single PolicyCondition from a ConditionTemplate.
   */
  private buildCondition(template: ConditionTemplate): PolicyCondition {
    const field = substituteVariables(template.field, this.resolvedParams);
    const valueStr = substituteVariables(template.value, this.resolvedParams);
    const description = template.description
      ? substituteVariables(template.description, this.resolvedParams)
      : undefined;

    // Parse value based on operator expectations
    let value: unknown = valueStr;
    // Try to parse as number
    if (/^-?\d+(\.\d+)?$/.test(valueStr)) {
      value = parseFloat(valueStr);
    }
    // Try to parse as boolean
    else if (valueStr === "true") {
      value = true;
    } else if (valueStr === "false") {
      value = false;
    }
    // Try to parse as JSON (for arrays/objects)
    else if (valueStr.startsWith("[") || valueStr.startsWith("{")) {
      try {
        value = JSON.parse(valueStr);
      } catch {
        // Keep as string
      }
    }

    return {
      field,
      operator: template.operator as ConditionOperator,
      value,
      description,
    };
  }

  /**
   * Build a single PolicyTestCase from a TestCaseTemplate.
   */
  private buildTestCase(template: TestCaseTemplate): import("./types").PolicyTestCase {
    const name = substituteVariables(template.name, this.resolvedParams);
    const resource = substituteVariables(template.resource, this.resolvedParams);
    const action = substituteVariables(template.action, this.resolvedParams);
    const context = substituteDeep(template.context, this.resolvedParams);
    const expected = substituteVariables(template.expected, this.resolvedParams) as import("./types").PolicyTestExpectation;
    const description = template.description
      ? substituteVariables(template.description, this.resolvedParams)
      : undefined;

    return {
      name,
      resource,
