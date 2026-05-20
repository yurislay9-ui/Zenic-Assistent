import {
  TIER_LIMITS,
  TIER_DISPLAY_NAMES,
  FEATURE_TIER_MAP,
} from "@/lib/pricing-engine/types";
import type {
  SubscriptionTierName,
  FeatureName,
} from "@/lib/pricing-engine/types";
import type { FeatureGateUI, ContextoSuscripcion } from "./types";

// ═══════════════════════════════════════════════════════════════════════════════
// FEATURE GATES — Mapeo de widgets y menús a features del sistema
// ═══════════════════════════════════════════════════════════════════════════════

export const WIDGET_GATES: Array<{
  widget: string;
  feature: FeatureName;
  etiqueta: string;
  descripcion: string;
}> = [
  {
    widget: "mcp_gateway",
    feature: "McpCustomTools",
    etiqueta: "Gateway de Conexiones",
    descripcion: "Registro y gestión de herramientas personalizadas",
  },
  {
    widget: "policy_simulation",
    feature: "PolicySimulation",
    etiqueta: "Simulación de Políticas",
    descripcion: "Análisis what-if antes de desplegar cambios",
  },
  {
    widget: "z3_solver",
    feature: "PolicyZ3Solver",
    etiqueta: "Detección Z3 de Conflictos",
    descripcion: "Verificación formal de contradicciones en políticas",
  },
  {
    widget: "dry_run",
    feature: "PolicySimulation",
    etiqueta: "Simulación en Seco",
    descripcion: "Ejecución de prueba antes de aprobación final",
  },
  {
    widget: "hitl_evidence",
    feature: "HitlEvidence",
    etiqueta: "Evidencia Detallada",
    descripcion: "Balanzas de evidencia para cada veredicto",
  },
  {
    widget: "hitl_delegation",
    feature: "HitlDelegation",
    etiqueta: "Delegación de Aprobaciones",
    descripcion: "Delegar decisiones a otros revisores",
  },
  {
    widget: "hitl_escalation",
    feature: "HitlEscalation",
    etiqueta: "Escalamiento Automático",
    descripcion: "Escalar solicitudes por tiempo o prioridad",
  },
  {
    widget: "merkle_chain",
    feature: "AuditMerkleChain",
    etiqueta: "Cadena de Registro Completa",
    descripcion: "Registro inmutable con verificación criptográfica",
  },
  {
    widget: "compliance_export",
    feature: "AuditComplianceExport",
    etiqueta: "Exportar Cumplimiento",
    descripcion: "Exportar informes de auditoría normativos",
  },
  {
    widget: "custom_dashboards",
    feature: "ObservabilityCustomDashboards",
    etiqueta: "Dashboards Personalizados",
    descripcion: "Crear vistas de observabilidad a medida",
  },
  {
    widget: "policy_impact",
    feature: "PolicyImpactAnalysis",
    etiqueta: "Análisis de Impacto",
    descripcion: "Radio de explosión y dependencias por cambio",
  },
  {
    widget: "sso",
    feature: "RbacSsoIntegration",
    etiqueta: "SSO / Integración SAML",
    descripcion: "Autenticación single sign-on empresarial",
  },
];

/** Determinar el tier mínimo requerido para una feature */
export function tierMinimo(feature: FeatureName): SubscriptionTierName {
  const tiers = FEATURE_TIER_MAP[feature];
  if (!tiers || tiers.length === 0) return "on_premise_enterprise";
  if (tiers.includes("starter")) return "starter";
  if (tiers.includes("business")) return "business";
  if (tiers.includes("enterprise")) return "enterprise";
  return "on_premise_enterprise";
}

/** Construir el contexto de suscripción completo */
export function construirContextoSuscripcion(
  tier: SubscriptionTierName
): ContextoSuscripcion {
  const limites = TIER_LIMITS[tier];
  const nombreMostrar = TIER_DISPLAY_NAMES[tier] ?? tier;

  const caracteristicas: FeatureGateUI[] = WIDGET_GATES.map((wg) => {
    const tiersPermitidos = FEATURE_TIER_MAP[wg.feature];
    const disponible = tiersPermitidos?.includes(tier) ?? false;
    return {
      feature: wg.feature,
      etiqueta: wg.etiqueta,
      descripcion: wg.descripcion,
      tierMinimo: tierMinimo(wg.feature),
      disponible,
    };
  });

  return { tier, nombreMostrar, limites, caracteristicas };
}
