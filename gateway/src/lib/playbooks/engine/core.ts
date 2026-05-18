
      return mapDbToRecord(playbook);
    } catch (error) {
      if (error instanceof PlaybookCompilationError) throw error;
      throw new PlaybookCompilationError(
        `Failed to create playbook: ${error instanceof Error ? error.message : String(error)}`,
        doc.metadata.id,
      );
    }
  }

  /**
   * Get a single playbook by its playbook ID.
   */
  async getPlaybook(playbookId: string): Promise<PlaybookDbRecord | null> {
    try {
      const playbook = await db.playbook.findFirst({
        where: { playbookId },
      });

      if (!playbook) return null;

      return mapDbToRecord(playbook);
    } catch (error) {
      throw new PlaybookCompilationError(
        `Failed to get playbook: ${error instanceof Error ? error.message : String(error)}`,
        playbookId,
      );
    }
  }

  /**
   * List playbooks with optional filters.
   */
  async listPlaybooks(filters?: {
    industry?: Industry;
    isActive?: boolean;
    certificationStatus?: CertificationStatus;
  }): Promise<PlaybookDbRecord[]> {
    try {
      const where: Record<string, unknown> = {};

      if (filters?.industry) {
        where.industry = filters.industry;
      }
      if (filters?.isActive !== undefined) {
        where.isActive = filters.isActive;
      }
      if (filters?.certificationStatus) {
        where.certificationStatus = filters.certificationStatus;
      }

      const playbooks = await db.playbook.findMany({
        where,
        orderBy: { updatedAt: "desc" },
      });

      return playbooks.map(mapDbToRecord);
    } catch (error) {
      throw new PlaybookCompilationError(
        `Failed to list playbooks: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }

  /**
   * Update an existing playbook with a new PlaybookDocument.
   */
  async updatePlaybook(
    playbookId: string,
    doc: PlaybookDocument,
  ): Promise<PlaybookDbRecord> {
    try {
      const existing = await db.playbook.findFirst({
        where: { playbookId },
      });

      if (!existing) {
        throw new PlaybookCompilationError(
          `Playbook "${playbookId}" not found`,
          playbookId,
        );
      }

      const contentHash = computePlaybookContentHash(doc);

      const playbook = await db.playbook.update({
        where: { id: existing.id },
        data: {
          name: doc.metadata.name,
          nameEn: doc.metadata.name_en,
          industry: doc.metadata.industry,
          subIndustry: doc.metadata.sub_industry,
          version: doc.metadata.version,
          description: doc.metadata.description,
          icon: doc.metadata.icon,
          color: doc.metadata.color,
          labels: JSON.stringify(doc.metadata.labels),
          compliance: JSON.stringify(doc.metadata.compliance),
          capabilities: JSON.stringify(doc.capabilities),
          policies: JSON.stringify(doc.policies),
          roiConfig: JSON.stringify(doc.roi),
          pricing: JSON.stringify(doc.pricing),
          onboarding: JSON.stringify(doc.onboarding),
          certificationStatus: doc.certification.status,
          certificationSignedBy: doc.certification.signedBy,
          certificationSignedAt: doc.certification.signedAt ? new Date(doc.certification.signedAt) : null,
          certificationSignature: doc.certification.signature,
          certificationHash: doc.certification.contentHash,
          contentHash,
          author: doc.metadata.author,
        },
      });

      // Invalidate cache
      this.invalidateCache(playbookId);

      return mapDbToRecord(playbook);
    } catch (error) {
      if (error instanceof PlaybookCompilationError) throw error;
      throw new PlaybookCompilationError(
        `Failed to update playbook: ${error instanceof Error ? error.message : String(error)}`,
        playbookId,
      );
    }
  }

  /**
   * Deactivate a playbook (soft delete — sets isActive to false).
   */
  async deactivatePlaybook(playbookId: string): Promise<PlaybookDbRecord> {
    try {
      const existing = await db.playbook.findFirst({
        where: { playbookId },
      });

      if (!existing) {
        throw new PlaybookCompilationError(
          `Playbook "${playbookId}" not found`,
          playbookId,
        );
      }

      const playbook = await db.playbook.update({
        where: { id: existing.id },
        data: { isActive: false },
      });

      this.invalidateCache(playbookId);

      return mapDbToRecord(playbook);
    } catch (error) {
      if (error instanceof PlaybookCompilationError) throw error;
      throw new PlaybookCompilationError(
        `Failed to deactivate playbook: ${error instanceof Error ? error.message : String(error)}`,
        playbookId,
      );
    }
  }

  /**
   * Search playbooks by structured criteria.
   */
  async searchPlaybooks(criteria: PlaybookSearchCriteria): Promise<PlaybookSearchResult> {
    try {
      const where: Record<string, unknown> = {};

      if (criteria.industry) {
        where.industry = criteria.industry;
      }
      if (criteria.sub_industry) {
        where.subIndustry = { contains: criteria.sub_industry };
      }
      if (criteria.certificationStatus) {
        where.certificationStatus = criteria.certificationStatus;
      }
      if (criteria.status === PlaybookStatusEnum.ACTIVE) {
        where.isActive = true;
      }
      if (criteria.maxPriceUsdt !== undefined) {
        // Price filtering requires post-query JSON parsing
      }

      const playbooks = await db.playbook.findMany({
        where,
        orderBy: { updatedAt: "desc" },
      });

      // Post-filter with criteria that require JSON field inspection
      let results = playbooks.map(mapDbToRecord);

      if (criteria.capabilityId) {
        results = results.filter((p) =>
          p.capabilities.some((c) => c.id === criteria.capabilityId),
        );
      }

      if (criteria.minRoiPercentage !== undefined) {
        results = results.filter((p) => {
          const roi = p.roiConfig.calculated;
          return roi && roi.roi_percentage >= (criteria.minRoiPercentage ?? 0);
        });
      }

      if (criteria.maxPriceUsdt !== undefined) {
        results = results.filter((p) => {
          const starterTier = p.pricing.tiers[0];
          return starterTier && starterTier.price_usdt <= (criteria.maxPriceUsdt ?? Infinity);
        });
      }

      if (criteria.compliance) {
        results = results.filter((p) =>
          p.compliance.includes(criteria.compliance!),
        );
      }

      if (criteria.searchQuery) {
        const query = criteria.searchQuery.toLowerCase();
        results = results.filter((p) =>
          p.name.toLowerCase().includes(query) ||
          p.description.toLowerCase().includes(query) ||
          Object.values(p.labels).some((v) => v.toLowerCase().includes(query)),
        );
      }

      if (criteria.labels) {
        for (const [key, value] of Object.entries(criteria.labels)) {
          results = results.filter((p) => p.labels[key] === value);
        }
      }

      return {
        playbooks: results.map((r) => r.document),
        total: results.length,
        offset: 0,
        limit: 100,
      };
    } catch (error) {
      throw new PlaybookCompilationError(
        `Failed to search playbooks: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }

  // ─── Evaluation ───────────────────────────────────────────────────

  /**
   * Evaluate a playbook's compatibility for a tenant.
   * Scores based on industry match, capabilities coverage, and policy availability.
   */
  async evaluatePlaybook(
    playbookId: string,
    tenantId?: string,
  ): Promise<PlaybookEvaluationResult> {
    try {
      const playbook = await db.playbook.findFirst({
        where: { playbookId },
      });

      if (!playbook) {
        return {
          compatible: false,
          score: 0,
          missingPolicies: [],
          suggestedPolicies: [],
          warnings: [`Playbook "${playbookId}" not found`],
        };
      }

      const warnings: string[] = [];
      const missingPolicies: string[] = [];
      const suggestedPolicies: string[] = [];

      // Check if playbook is active
      if (!playbook.isActive) {
        warnings.push(`Playbook "${playbookId}" is not active`);
      }

      // Check certification status
      if (playbook.certificationStatus !== CertificationStatusEnum.CERTIFIED) {
        warnings.push(
          `Playbook "${playbookId}" is not certified (status: ${playbook.certificationStatus}). ` +
          "Certified playbooks are recommended for production use.",
        );
      }

      // Parse policies and check availability
      const policies: PolicyReference[] = JSON.parse(playbook.policies);
      const requiredPolicyIds = policies
        .filter((p) => p.required)
        .map((p) => p.policyId);
      const optionalPolicyIds = policies
        .filter((p) => !p.required)
        .map((p) => p.policyId);

      // Check which policies exist in the system
      const existingPolicies = await db.declPolicy.findMany({
        where: {
          policyId: { in: [...requiredPolicyIds, ...optionalPolicyIds] },
          isActive: true,
        },
        select: { policyId: true },
      });
      const existingPolicyIds = new Set(existingPolicies.map((p) => p.policyId));

      for (const policyId of requiredPolicyIds) {
        if (!existingPolicyIds.has(policyId)) {
          missingPolicies.push(policyId);
        }
      }

      for (const policyId of optionalPolicyIds) {
        if (!existingPolicyIds.has(policyId)) {
          suggestedPolicies.push(policyId);
        }
      }

      // Calculate score (0-100)
      let score = 0;

      // Base score for active playbook (40 points)
      if (playbook.isActive) {
        score += 40;
      }

      // Certification bonus (20 points)
      if (playbook.certificationStatus === CertificationStatusEnum.CERTIFIED) {
        score += 20;
      } else if (playbook.certificationStatus === CertificationStatusEnum.PENDING) {
        score += 10;
      }

      // Policy coverage score (30 points)
      const totalRequired = requiredPolicyIds.length;
      const coveredRequired = requiredPolicyIds.filter((id) => existingPolicyIds.has(id)).length;
      if (totalRequired > 0) {
        score += Math.round((coveredRequired / totalRequired) * 30);
      } else {
        // No required policies — full coverage score
        score += 30;
      }

      // Capabilities score (10 points)
      const capabilities: PlaybookCapability[] = JSON.parse(playbook.capabilities);
      const autoEnabledCount = capabilities.filter((c) => c.autoEnabled).length;
      if (capabilities.length > 0) {
        score += Math.min(10, Math.round((autoEnabledCount / capabilities.length) * 10));
      }

