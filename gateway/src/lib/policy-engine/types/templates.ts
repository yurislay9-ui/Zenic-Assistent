// ─── 5. Policy Template Engine ──────────────────────────────────────────

/** Template API version */
export const TEMPLATE_API_VERSION = "template.zenic.dev/v1" as const;

/** Template document kind */
export const TEMPLATE_KIND = "PolicyTemplate" as const;

/** A policy template with parameterized variables */
export interface PolicyTemplate {
  /** API version */
  apiVersion: typeof TEMPLATE_API_VERSION;
  /** Document kind */
  kind: typeof TEMPLATE_KIND;
  /** Template metadata */
  metadata: TemplateMetadata;
  /** Template parameters */
  parameters: TemplateParameter[];
  /** Policy document template (with variable placeholders) */
  documentTemplate: PolicyDocumentTemplate;
  /** Default values for parameters */
  defaults: Record<string, unknown>;
  /** Constraint rules for parameter values */
  constraints: TemplateConstraint[];
  /** Generated policy count */
  generatedCount: number;
}

/** Template metadata */
export interface TemplateMetadata {
  /** Unique template identifier */
  id: string;
  /** Template name */
  name: string;
  /** Semantic version */
  version: string;
  /** Description */
  description: string;
  /** Category (e.g., "compliance", "security", "industry") */
  category: string;
  /** Industry this template targets */
  industry?: string;
  /** Tags */
  tags?: string[];
  /** Author */
  author?: string;
  /** Creation timestamp */
  createdAt?: string;
  /** Last update timestamp */
  updatedAt?: string;
}

/** A template parameter definition */
export interface TemplateParameter {
  /** Parameter name (used as {{paramName}} in templates) */
  name: string;
  /** Display name */
  displayName: string;
  /** Description */
  description: string;
  /** Parameter type */
  type: TemplateParameterType;
  /** Whether this parameter is required */
  required: boolean;
  /** Default value */
  defaultValue?: unknown;
  /** Allowed values (for enum type) */
  allowedValues?: unknown[];
  /** Validation regex (for string type) */
  validationRegex?: string;
  /** Min value (for number type) */
  minValue?: number;
  /** Max value (for number type) */
  maxValue?: number;
}

/** Template parameter types */
export const TemplateParameterType = {
  STRING: "string",
  NUMBER: "number",
  BOOLEAN: "boolean",
  ENUM: "enum",
  ARRAY: "array",
  OBJECT: "object",
  RESOURCE_PATTERN: "resource_pattern",
  ACTION_PATTERN: "action_pattern",
} as const;
export type TemplateParameterType = (typeof TemplateParameterType)[keyof typeof TemplateParameterType];

/** A policy document template with variable placeholders */
export interface PolicyDocumentTemplate {
  /** Template for metadata.name (supports {{variable}}) */
  name: string;
  /** Template for metadata.description */
  description: string;
  /** Statement templates */
  statements: StatementTemplate[];
  /** Test case templates */
  tests?: TestCaseTemplate[];
  /** Compliance mappings */
  compliance?: ComplianceMapping[];
  /** Labels template */
  labels?: Record<string, string>;
}

/** A statement template with variable placeholders */
export interface StatementTemplate {
  /** Statement ID template */
  id: string;
  /** Effect (can be {{variable}}) */
  effect: string;
  /** Resource pattern template */
  resource: string;
  /** Action pattern template */
  action: string;
  /** Condition templates */
  conditions?: ConditionTemplate[];
  /** Priority (can be {{variable}}) */
  priority: number | string;
  /** Description template */
  description?: string;
  /** Required role template */
  requiredRole?: string;
  /** Tags template */
  tags?: string[];
}

/** A condition template with variable placeholders */
export interface ConditionTemplate {
  /** Field path template */
  field: string;
  /** Operator */
  operator: ConditionOperator;
  /** Value template (can be {{variable}}) */
  value: string;
  /** Description template */
  description?: string;
}

/** A test case template */
export interface TestCaseTemplate {
  /** Test name template */
  name: string;
  /** Resource template */
  resource: string;
  /** Action template */
  action: string;
  /** Context template */
  context: Record<string, string>;
  /** Expected outcome */
  expected: string;
  /** Description template */
  description?: string;
}

/** Template constraint rules */
export interface TemplateConstraint {
  /** Constraint name */
  name: string;
  /** Constraint type */
  type: TemplateConstraintType;
  /** Parameters for the constraint */
  parameters: Record<string, unknown>;
  /** Error message on violation */
  errorMessage: string;
}

/** Template constraint types */
export const TemplateConstraintType = {
  MUTUALLY_EXCLUSIVE: "mutually_exclusive",     // Parameters cannot both be set
  REQUIRES: "requires",                         // One parameter requires another
  RANGE_CONSTRAINT: "range_constraint",         // Numeric range validation
  REGEX_CONSTRAINT: "regex_constraint",         // String pattern validation
  CUSTOM_EXPRESSION: "custom_expression",       // Custom boolean expression
} as const;
export type TemplateConstraintType = (typeof TemplateConstraintType)[keyof typeof TemplateConstraintType];

/** Template instantiation request */
export interface TemplateInstantiationRequest {
  /** Template ID */
  templateId: string;
  /** Parameter values */
  parameters: Record<string, unknown>;
  /** Target policy ID (for the generated policy) */
  targetPolicyId?: string;
  /** Whether to auto-deploy the generated policy */
  autoDeploy: boolean;
  /** Requested by */
  requestedBy: string;
}

/** Template instantiation result */
export interface TemplateInstantiationResult {
  /** Success */
  success: boolean;
  /** Generated policy document */
  document?: PolicyDocument;
  /** Validation errors */
  errors: string[];
  /** Warnings */
  warnings: string[];
  /** Generated policy ID */
  policyId?: string;
  /** Unresolved parameters */
  unresolvedParameters: string[];
}

