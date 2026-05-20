      action,
      context: context as Record<string, unknown>,
      expected,
      description,
    };
  }
}

// ─── DB Record Mapping ────────────────────────────────────────────────

/** Flattened record from DB with parsed JSON fields */
export interface TemplateDbRecord {
  id: string;
  templateId: string;
  name: string;
  version: string;
  description: string;
  category: string;
  industry: string | null;
  tags: string[];
  parameters: TemplateParameter[];
  documentTemplate: PolicyDocumentTemplate;
  defaults: Record<string, unknown>;
  constraints: TemplateConstraint[];
  generatedCount: number;
  isActive: boolean;
  author: string | null;
  sourceYaml: string | null;
  contentHash: string;
  createdAt: Date;
  updatedAt: Date;
}

/**
 * Map a Prisma PolicyTemplate record to a typed TemplateDbRecord.
 */
function mapDbToRecord(record: {
  id: string;
  templateId: string;
  name: string;
  version: string;
  description: string;
  category: string;
  industry: string | null;
  tags: string;
  parameters: string;
  documentTemplate: string;
  defaults: string;
  constraints: string;
  generatedCount: number;
  isActive: boolean;
  author: string | null;
  sourceYaml: string | null;
  contentHash: string;
  createdAt: Date;
  updatedAt: Date;
}): TemplateDbRecord {
  return {
    id: record.id,
    templateId: record.templateId,
    name: record.name,
    version: record.version,
    description: record.description,
    category: record.category,
    industry: record.industry,
    tags: JSON.parse(record.tags),
    parameters: JSON.parse(record.parameters),
    documentTemplate: JSON.parse(record.documentTemplate),
    defaults: JSON.parse(record.defaults),
    constraints: JSON.parse(record.constraints),
    generatedCount: record.generatedCount,
    isActive: record.isActive,
    author: record.author,
    sourceYaml: record.sourceYaml,
    contentHash: record.contentHash,
    createdAt: record.createdAt,
    updatedAt: record.updatedAt,
  };
}

/**
 * Reconstruct a full PolicyTemplate type from a DB record.
 */
function dbRecordToTemplate(record: TemplateDbRecord): PolicyTemplate {
  return {
    apiVersion: TEMPLATE_API_VERSION,
    kind: TEMPLATE_KIND,
    metadata: {
      id: record.templateId,
      name: record.name,
      version: record.version,
      description: record.description,
      category: record.category,
      industry: record.industry ?? undefined,
      tags: record.tags,
      author: record.author ?? undefined,
      createdAt: record.createdAt.toISOString(),
      updatedAt: record.updatedAt.toISOString(),
    },
    parameters: record.parameters,
    documentTemplate: record.documentTemplate,
    defaults: record.defaults,
    constraints: record.constraints,
    generatedCount: record.generatedCount,
  };
}

// ─── Public API Functions ─────────────────────────────────────────────

/**
 * Create a new policy template in the database.
 * Validates template structure, parameter definitions, and constraint rules.
 * Computes content hash for integrity.
 */
export async function createTemplate(
  template: PolicyTemplate,
): Promise<TemplateDbRecord> {
  // 1. Validate template structure
  const structureErrors = validateTemplateStructure(template);
  if (structureErrors.length > 0) {
    throw new TemplateValidationError(
      `Template validation failed: ${structureErrors.join("; ")}`,
      "root",
    );
  }

  // 2. Check for duplicate templateId
  const existing = await db.policyTemplate.findUnique({
    where: { templateId: template.metadata.id },
  });
  if (existing) {
    throw new TemplateValidationError(
      `Template with ID "${template.metadata.id}" already exists`,
      "metadata.id",
      template.metadata.id,
    );
  }

  // 3. Compute content hash
  const contentHash = computeTemplateContentHash(template);

  // 4. Persist to database
  try {
    const created = await db.policyTemplate.create({
      data: {
        templateId: template.metadata.id,
        name: template.metadata.name,
        version: template.metadata.version,
        description: template.metadata.description,
        category: template.metadata.category,
        industry: template.metadata.industry ?? null,
        tags: JSON.stringify(template.metadata.tags ?? []),
        parameters: JSON.stringify(template.parameters),
        documentTemplate: JSON.stringify(template.documentTemplate),
        defaults: JSON.stringify(template.defaults),
        constraints: JSON.stringify(template.constraints),
        generatedCount: 0,
        isActive: true,
        author: template.metadata.author ?? null,
        contentHash,
      },
    });

    return mapDbToRecord(created);
  } catch (error) {
    throw new TemplateValidationError(
      `Failed to create template: ${error instanceof Error ? error.message : String(error)}`,
      "root",
    );
  }
}

/**
 * Get a template by its templateId.
 */
export async function getTemplate(
  templateId: string,
): Promise<TemplateDbRecord | null> {
  try {
    const record = await db.policyTemplate.findUnique({
      where: { templateId },
    });

    if (!record) return null;
    return mapDbToRecord(record);
  } catch (error) {
    throw new TemplateValidationError(
      `Failed to get template "${templateId}": ${error instanceof Error ? error.message : String(error)}`,
      "templateId",
      templateId,
    );
  }
}

/** Options for listing templates */
export interface ListTemplatesOptions {
  /** Filter by category */
  category?: string;
  /** Filter by industry */
  industry?: string;
  /** Filter by active status */
  isActive?: boolean;
  /** Maximum number of results */
  limit?: number;
  /** Offset for pagination */
  offset?: number;
}

/**
 * List templates with optional filtering.
 */
export async function listTemplates(
  options?: ListTemplatesOptions,
): Promise<TemplateDbRecord[]> {
  try {
    const where: Record<string, unknown> = {};

    if (options?.category !== undefined) {
      where.category = options.category;
    }
    if (options?.industry !== undefined) {
      where.industry = options.industry;
    }
    if (options?.isActive !== undefined) {
      where.isActive = options.isActive;
    }

    const records = await db.policyTemplate.findMany({
      where,
      orderBy: { createdAt: "desc" },
      take: options?.limit ?? 100,
      skip: options?.offset ?? 0,
    });

    return records.map(mapDbToRecord);
  } catch (error) {
    throw new TemplateValidationError(
      `Failed to list templates: ${error instanceof Error ? error.message : String(error)}`,
      "root",
    );
  }
}

/**
 * Instantiate a template — generate a PolicyDocument from a template with parameter substitution.
 *
 * Pipeline:
 *   1. Load template from DB
 *   2. Resolve parameters (provided → defaults → unresolved)
 *   3. Validate all required parameters have values
 *   4. Apply parameter type validation
 *   5. Validate constraint rules
 *   6. Substitute {{variable}} placeholders in documentTemplate
 *   7. Generate a complete PolicyDocument via Builder
 *   8. If autoDeploy=true → store to DeclPolicy
 *   9. Increment template's generatedCount
 *  10. Return TemplateInstantiationResult
 */
export async function instantiateTemplate(
  request: TemplateInstantiationRequest,
): Promise<TemplateInstantiationResult> {
  const errors: string[] = [];
  const warnings: string[] = [];

  // 1. Load template from DB
  let dbRecord: TemplateDbRecord;
  try {
    const record = await getTemplate(request.templateId);
    if (!record) {
      return {
        success: false,
        errors: [`Template "${request.templateId}" not found`],
        warnings: [],
        unresolvedParameters: [],
      };
    }
    if (!record.isActive) {
      return {
        success: false,
        errors: [`Template "${request.templateId}" is not active`],
        warnings: [],
        unresolvedParameters: [],
      };
    }
    dbRecord = record;
  } catch (error) {
    return {
      success: false,
      errors: [`Failed to load template: ${error instanceof Error ? error.message : String(error)}`],
      warnings: [],
      unresolvedParameters: [],
    };
  }

  const template = dbRecordToTemplate(dbRecord);

  // 2. Resolve parameters: provided values → defaults → unresolved
  const resolvedParams: Record<string, unknown> = {};
  const unresolvedParameters: string[] = [];

