const PARAMETER_TYPE_VALIDATORS: Record<TemplateParameterType, (value: unknown, param: TemplateParameter) => ParameterValidationResult> = {
  [TemplateParameterType.STRING]: (value, param) => {
    if (typeof value !== "string") {
      return { valid: false, error: `Parameter "${param.name}" must be a string, got ${typeof value}` };
    }
    if (param.validationRegex) {
      try {
        const regex = new RegExp(param.validationRegex);
        if (!regex.test(value)) {
          return { valid: false, error: `Parameter "${param.name}" value "${value}" does not match regex "${param.validationRegex}"` };
        }
      } catch {
        return { valid: false, error: `Parameter "${param.name}" has invalid validationRegex "${param.validationRegex}"` };
      }
    }
    return { valid: true };
  },

  [TemplateParameterType.NUMBER]: (value, param) => {
    if (typeof value !== "number" || isNaN(value)) {
      return { valid: false, error: `Parameter "${param.name}" must be a number, got ${typeof value}` };
    }
    if (param.minValue !== undefined && value < param.minValue) {
      return { valid: false, error: `Parameter "${param.name}" value ${value} is below minimum ${param.minValue}` };
    }
    if (param.maxValue !== undefined && value > param.maxValue) {
      return { valid: false, error: `Parameter "${param.name}" value ${value} exceeds maximum ${param.maxValue}` };
    }
    return { valid: true };
  },

  [TemplateParameterType.BOOLEAN]: (value, param) => {
    if (typeof value !== "boolean") {
      return { valid: false, error: `Parameter "${param.name}" must be a boolean, got ${typeof value}` };
    }
    return { valid: true };
  },

  [TemplateParameterType.ENUM]: (value, param) => {
    if (!param.allowedValues || param.allowedValues.length === 0) {
      return { valid: false, error: `Parameter "${param.name}" has no allowedValues defined for enum type` };
    }
    if (!param.allowedValues.includes(value)) {
      return { valid: false, error: `Parameter "${param.name}" value "${String(value)}" is not in allowed values: [${param.allowedValues.map(String).join(", ")}]` };
    }
    return { valid: true };
  },

  [TemplateParameterType.ARRAY]: (value, param) => {
    if (!Array.isArray(value)) {
      return { valid: false, error: `Parameter "${param.name}" must be an array, got ${typeof value}` };
    }
    return { valid: true };
  },

  [TemplateParameterType.OBJECT]: (value, param) => {
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
      return { valid: false, error: `Parameter "${param.name}" must be an object, got ${value === null ? "null" : Array.isArray(value) ? "array" : typeof value}` };
    }
    return { valid: true };
  },

  [TemplateParameterType.RESOURCE_PATTERN]: (value, param) => {
    if (typeof value !== "string") {
      return { valid: false, error: `Parameter "${param.name}" must be a string for resource_pattern, got ${typeof value}` };
    }
    if (/\s/.test(value)) {
      return { valid: false, error: `Parameter "${param.name}" resource_pattern "${value}" must not contain spaces` };
    }
    return { valid: true };
  },

  [TemplateParameterType.ACTION_PATTERN]: (value, param) => {
    if (typeof value !== "string") {
      return { valid: false, error: `Parameter "${param.name}" must be a string for action_pattern, got ${typeof value}` };
    }
    if (/\s/.test(value)) {
      return { valid: false, error: `Parameter "${param.name}" action_pattern "${value}" must not contain spaces` };
    }
    return { valid: true };
  },
};

/**
 * Validate a single parameter value against its type definition.
 * Uses Strategy pattern — dispatches to the appropriate type validator.
 */
function validateParameterType(
  value: unknown,
  param: TemplateParameter,
): ParameterValidationResult {
  const validator = PARAMETER_TYPE_VALIDATORS[param.type];
  if (!validator) {
    return { valid: false, error: `Unknown parameter type "${param.type}" for parameter "${param.name}"` };
  }
  return validator(value, param);
}

// ─── Constraint Validation ────────────────────────────────────────────

/** Result of constraint validation */
interface ConstraintValidationResult {
  valid: boolean;
  errors: string[];
}

/**
 * Validate all constraint rules against resolved parameter values.
 * Each constraint type has its own validation logic.
 */
function validateConstraints(
  constraints: TemplateConstraint[],
  resolvedParams: Record<string, unknown>,
): ConstraintValidationResult {
  const errors: string[] = [];

  for (const constraint of constraints) {
    switch (constraint.type) {
      case TemplateConstraintType.MUTUALLY_EXCLUSIVE: {
        const params = constraint.parameters.parameters as string[];
        if (!Array.isArray(params) || params.length < 2) {
          errors.push(`Constraint "${constraint.name}": mutually_exclusive requires at least 2 parameters`);
          break;
        }
        const param0 = params[0]!;
        const param1 = params[1]!;
        const hasParam0 = param0 in resolvedParams && resolvedParams[param0] !== undefined && resolvedParams[param0] !== null;
        const hasParam1 = param1 in resolvedParams && resolvedParams[param1] !== undefined && resolvedParams[param1] !== null;
        if (hasParam0 && hasParam1) {
          errors.push(constraint.errorMessage || `Parameters "${param0}" and "${param1}" are mutually exclusive`);
        }
        break;
      }

      case TemplateConstraintType.REQUIRES: {
        const params = constraint.parameters.parameters as string[];
        if (!Array.isArray(params) || params.length < 2) {
          errors.push(`Constraint "${constraint.name}": requires constraint needs at least 2 parameters`);
          break;
        }
        const param0 = params[0]!;
        const param1 = params[1]!;
        const hasParam0 = param0 in resolvedParams && resolvedParams[param0] !== undefined && resolvedParams[param0] !== null;
        const hasParam1 = param1 in resolvedParams && resolvedParams[param1] !== undefined && resolvedParams[param1] !== null;
        if (hasParam0 && !hasParam1) {
          errors.push(constraint.errorMessage || `Parameter "${param0}" requires "${param1}" to also be set`);
        }
        break;
      }

      case TemplateConstraintType.RANGE_CONSTRAINT: {
        const paramName = constraint.parameters.parameter as string;
        const min = constraint.parameters.min as number | undefined;
        const max = constraint.parameters.max as number | undefined;
        const value = resolvedParams[paramName];

        if (value !== undefined && value !== null && typeof value === "number") {
          if (min !== undefined && value < min) {
            errors.push(constraint.errorMessage || `Parameter "${paramName}" value ${value} is below minimum ${min}`);
          }
          if (max !== undefined && value > max) {
            errors.push(constraint.errorMessage || `Parameter "${paramName}" value ${value} exceeds maximum ${max}`);
          }
        }
        break;
      }

      case TemplateConstraintType.REGEX_CONSTRAINT: {
        const paramName = constraint.parameters.parameter as string;
        const pattern = constraint.parameters.regex as string;
        const value = resolvedParams[paramName];

        if (value !== undefined && value !== null && typeof value === "string") {
          try {
            const regex = new RegExp(pattern);
            if (!regex.test(value)) {
              errors.push(constraint.errorMessage || `Parameter "${paramName}" value "${value}" does not match regex "${pattern}"`);
            }
          } catch {
            errors.push(`Constraint "${constraint.name}": invalid regex pattern "${pattern}"`);
          }
        }
        break;
      }

      case TemplateConstraintType.CUSTOM_EXPRESSION: {
        const expression = constraint.parameters.expression as string;
        if (typeof expression !== "string") {
          errors.push(`Constraint "${constraint.name}": custom_expression requires an expression string`);
          break;
        }
        const result = evaluateCustomExpression(expression, resolvedParams);
        if (!result) {
          errors.push(constraint.errorMessage || `Custom expression "${expression}" evaluated to false`);
        }
        break;
      }

      default:
        errors.push(`Unknown constraint type "${constraint.type}" on constraint "${constraint.name}"`);
    }
  }

  return { valid: errors.length === 0, errors };
}

/**
 * Evaluate a simple custom boolean expression.
 * Supports basic comparisons: param1 == "value", param1 != "value",
 * param1 > 10, param1 < 10, param1 >= 10, param1 <= 10
 * AND logical operators: expr1 && expr2
 */
function evaluateCustomExpression(
  expression: string,
  resolvedParams: Record<string, unknown>,
): boolean {
  // Split on && for AND logic
  const parts = expression.split("&&").map((s) => s.trim());

  return parts.every((part) => {
    // Try comparison operators (order matters: >= before >, <= before <)
    const compMatch = part.match(/^(\w+)\s*(>=|<=|!=|==|>|<)\s*(.+)$/);
    if (!compMatch) return false;

    const [, paramName, operator, rawValue] = compMatch;
    const paramValue = resolvedParams[paramName!];

    // Parse the comparison value
    let compValue: unknown = rawValue!.trim();
    const trimmed = rawValue!.trim();

    // Try number
    if (/^-?\d+(\.\d+)?$/.test(trimmed)) {
      compValue = parseFloat(trimmed);
    }
    // Try boolean
    else if (trimmed === "true") {
      compValue = true;
    } else if (trimmed === "false") {
      compValue = false;
    }
    // Try quoted string
    else if ((trimmed.startsWith('"') && trimmed.endsWith('"')) || (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
      compValue = trimmed.slice(1, -1);
    }

    switch (operator) {
      case "==": return paramValue == compValue;
      case "!=": return paramValue != compValue;
      case ">": return typeof paramValue === "number" && typeof compValue === "number" && paramValue > compValue;
      case "<": return typeof paramValue === "number" && typeof compValue === "number" && paramValue < compValue;
      case ">=": return typeof paramValue === "number" && typeof compValue === "number" && paramValue >= compValue;
      case "<=": return typeof paramValue === "number" && typeof compValue === "number" && paramValue <= compValue;
      default: return false;
    }
  });
}

// ─── Template Structure Validation ────────────────────────────────────

const VALID_PARAMETER_TYPES: ReadonlySet<string> = new Set<string>([
  TemplateParameterType.STRING,
  TemplateParameterType.NUMBER,
  TemplateParameterType.BOOLEAN,
  TemplateParameterType.ENUM,
  TemplateParameterType.ARRAY,
  TemplateParameterType.OBJECT,
  TemplateParameterType.RESOURCE_PATTERN,
  TemplateParameterType.ACTION_PATTERN,
]);

const VALID_CONSTRAINT_TYPES: ReadonlySet<string> = new Set<string>([
  TemplateConstraintType.MUTUALLY_EXCLUSIVE,
  TemplateConstraintType.REQUIRES,
  TemplateConstraintType.RANGE_CONSTRAINT,
  TemplateConstraintType.REGEX_CONSTRAINT,
  TemplateConstraintType.CUSTOM_EXPRESSION,
]);

const VALID_EFFECTS: ReadonlySet<string> = new Set(["allow", "deny", "conditional"]);

/**
 * Validate the structure of a PolicyTemplate object.
 * Checks: apiVersion, kind, metadata, parameters, documentTemplate, constraints.
 * Returns an array of error strings (empty = valid).
 */
function validateTemplateStructure(template: PolicyTemplate): string[] {
  const errors: string[] = [];

  // apiVersion
  if (template.apiVersion !== TEMPLATE_API_VERSION) {
    errors.push(`Invalid apiVersion "${template.apiVersion}". Expected "${TEMPLATE_API_VERSION}"`);
  }

  // kind
  if (template.kind !== TEMPLATE_KIND) {
    errors.push(`Invalid kind "${template.kind}". Expected "${TEMPLATE_KIND}"`);
  }

  // metadata
