      const compatible = playbook.isActive && missingPolicies.length === 0;

      return {
        compatible,
        score: Math.min(100, score),
        missingPolicies,
        suggestedPolicies,
        warnings,
      };
    } catch (error) {
      return {
        compatible: false,
        score: 0,
        missingPolicies: [],
        suggestedPolicies: [],
        warnings: [`Evaluation error: ${error instanceof Error ? error.message : String(error)}`],
      };
    }
  }

  // ─── Activation ───────────────────────────────────────────────────

  /**
   * Activate a playbook for a tenant.
   * Links policies, configures tools, and calculates ROI projection.
   */
  async activatePlaybook(
    request: PlaybookActivationRequest,
  ): Promise<PlaybookActivationResult> {
    try {
      // 1. Validate playbook exists and is active
      const playbook = await db.playbook.findFirst({
        where: { playbookId: request.playbookId },
      });

      if (!playbook) {
        return {
          success: false,
          activatedPolicies: [],
          configuredTools: [],
          roiProjection: createDefaultRoiCalculation(),
          message: `Playbook "${request.playbookId}" not found`,
        };
      }

      if (!playbook.isActive) {
        return {
          success: false,
          activatedPolicies: [],
          configuredTools: [],
          roiProjection: createDefaultRoiCalculation(),
          message: `Playbook "${request.playbookId}" is not active`,
        };
      }

      // 2. Link policies — create DeclPolicy entries if needed
      const policies: PolicyReference[] = JSON.parse(playbook.policies);
      const activatedPolicies: string[] = [];

      for (const policyRef of policies) {
        // Check if policy already exists
        const existingPolicy = await db.declPolicy.findFirst({
          where: { policyId: policyRef.policyId },
        });

        if (existingPolicy) {
          // Ensure it's active
          if (!existingPolicy.isActive && policyRef.required) {
            await db.declPolicy.update({
              where: { id: existingPolicy.id },
              data: { isActive: true },
            });
          }
          activatedPolicies.push(policyRef.policyId);
        } else if (policyRef.required) {
          // Create a placeholder DeclPolicy for required policies
          await db.declPolicy.create({
            data: {
              policyId: policyRef.policyId,
              name: `Auto-created for playbook ${request.playbookId}`,
              description: policyRef.reason ?? `Auto-created policy reference from playbook "${request.playbookId}"`,
              apiVersion: "policy.zenic.dev/v1",
              version: "1.0.0",
              labels: JSON.stringify({ source: "playbook", playbookId: request.playbookId }),
              compliance: "[]",
              statements: JSON.stringify([{
                id: `${policyRef.policyId}-auto-allow`,
                effect: "allow",
                resource: "*",
                action: "*",
                priority: 0,
              }]),
              tests: "[]",
              isActive: true,
              contentHash: computePlaybookContentHash({
                apiVersion: "playbook.zenic.dev/v1",
                kind: "Playbook",
                metadata: {
                  id: policyRef.policyId,
                  name: `Auto-created for playbook ${request.playbookId}`,
                  name_en: "",
                  industry: playbook.industry as Industry,
                  sub_industry: "",
                  compliance: [],
                  icon: "",
                  color: "",
                  version: "1.0.0",
                  description: policyRef.reason ?? "",
                  author: "system",
                  labels: {},
                },
                capabilities: [],
                policies: [],
                roi: {
                  baseline: {
                    manual_time_per_action_min: 0,
                    error_rate_pct: 0,
                    actions_per_month: 0,
                    cost_per_error_usd: 0,
                    violations_per_year: 0,
                    penalty_per_violation_usd: 0,
                  },
                  projected: {
                    automated_time_per_action_min: 0,
                    reduced_error_rate_pct: 0,
                    compliance_score_target: 0,
                    automation_rate_pct: 0,
                  },
                  assumptions: [],
                },
                pricing: {
                  currency: "USDT",
                  network: "TRC20",
                  tiers: [
                    { name: PricingTierNameEnum.STARTER, price_usdt: 0, setup_fee_usdt: 0, features: [], limits: {}, recommended_for: "", payment_currency: "USDT", payment_network: "TRC20" },
                    { name: PricingTierNameEnum.BUSINESS, price_usdt: 0, setup_fee_usdt: 0, features: [], limits: {}, recommended_for: "", payment_currency: "USDT", payment_network: "TRC20" },
                    { name: PricingTierNameEnum.ENTERPRISE, price_usdt: 0, setup_fee_usdt: 0, features: [], limits: {}, recommended_for: "", payment_currency: "USDT", payment_network: "TRC20" },
                  ],
                },
                onboarding: { steps: [], estimated_minutes: 0 },
                certification: { status: CertificationStatusEnum.UNSIGNED },
              }),
            },
          });
          activatedPolicies.push(policyRef.policyId);
        }
      }

      // 3. Extract configured tools from capabilities
      const capabilities: PlaybookCapability[] = JSON.parse(playbook.capabilities);
      const configuredTools = capabilities
        .filter((c) => c.autoEnabled)
        .map((c) => c.id);

      // 4. Calculate ROI projection
      const roiConfig: PlaybookRoiConfig = JSON.parse(playbook.roiConfig);
      const pricingConfig: PlaybookPricing = JSON.parse(playbook.pricing);
      const selectedTier = pricingConfig.tiers.find((t) => t.name === request.selectedTier);
      const monthlyCostUsdt = selectedTier?.price_usdt ?? 0;

      let roiProjection: RoiCalculation;

      // Try lazy import of roi-calculator module
      try {
        const roiModule = await loadRoiCalculator();
        roiProjection = roiModule.calculateRoi({
          baseline: roiConfig.baseline,
          projected: roiConfig.projected,
          monthlyCostUsd: monthlyCostUsdt,
          workingHoursPerMonth: 160,
          hourlyCostUsd: 50,
        });
      } catch {
        // Fallback to inline calculation
        roiProjection = calculateRoiInline(roiConfig.baseline, roiConfig.projected, monthlyCostUsd);
      }

      // 5. Record activation in DB
      await db.playbookActivation.create({
        data: {
          playbookDbId: playbook.id,
          tenantId: request.tenantId,
          selectedTier: request.selectedTier,
          customConfig: JSON.stringify(request.customConfig ?? {}),
          activatedPolicies: JSON.stringify(activatedPolicies),
          configuredTools: JSON.stringify(configuredTools),
          roiProjection: JSON.stringify(roiProjection),
          status: "active",
        },
      });

      return {
        success: true,
        activatedPolicies,
        configuredTools,
        roiProjection,
        message: `Playbook "${request.playbookId}" activated successfully with ${activatedPolicies.length} policies and ${configuredTools.length} tools on ${request.selectedTier} tier`,
      };
    } catch (error) {
      return {
        success: false,
        activatedPolicies: [],
        configuredTools: [],
        roiProjection: createDefaultRoiCalculation(),
        message: `Activation failed: ${error instanceof Error ? error.message : String(error)}`,
      };
    }
  }

  /**
   * Deactivate a playbook activation.
   */
  async deactivateActivation(activationId: string): Promise<void> {
    try {
      const activation = await db.playbookActivation.findFirst({
        where: { id: activationId },
      });

      if (!activation) {
        throw new PlaybookCompilationError(
          `Activation "${activationId}" not found`,
        );
      }

      await db.playbookActivation.update({
        where: { id: activationId },
        data: {
          status: "deactivated",
          deactivatedAt: new Date(),
        },
      });
    } catch (error) {
      if (error instanceof PlaybookCompilationError) throw error;
      throw new PlaybookCompilationError(
        `Failed to deactivate activation: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }

  // ─── Cache Management ─────────────────────────────────────────────

  /**
   * Clear the document cache.
   */
  clearCache(): void {
    this.cache.clear();
  }

  /**
   * Invalidate cache for a specific playbook.
