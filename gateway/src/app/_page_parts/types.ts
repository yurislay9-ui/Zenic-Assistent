import type {
  SubscriptionTierName,
  FeatureName,
  TierLimitsInfo,
} from "@/lib/pricing-engine/types";

// ═══════════════════════════════════════════════════════════════════════════════
// TIPOS — Tipado estricto para todo el dashboard
// ═══════════════════════════════════════════════════════════════════════════════

export interface MetricasDashboard {
  activeAgents: number;
  hitlProposals: number;
  zeroHallucinationsPct: number;
  securityGateBlocks: number;
  executionsToday: number;
  successRate: number;
  avgExecutionTime: number;
  deniedExecutions: number;
  totalTools: number;
  activeTools: number;
  totalServers: number;
  healthyServers: number;
  pendingApprovals: number;
  criticalAlerts: number;
}

export interface PropuestaMemoria {
  id: string;
  requestId: string;
  title: string;
  description: string;
  type: string;
  status: string;
  priority: string;
  requesterName: string;
  targetAction: string;
  createdAt: string;
  llmVerdict: boolean;
}

export interface AlertaSNA {
  id: string;
  severity: string;
  action: string;
  resourceName: string;
  details: string;
  createdAt: string;
}

export interface EntradaLedger {
  id: string;
  requestId: string;
  eventType: string;
  actorName: string;
  contentHash: string;
  previousHash: string | null;
  timestamp: string;
}

export interface PasoPipeline {
  id: number;
  name: string;
  description: string;
  status: "active" | "idle" | "processing";
  throughput: number;
}

export interface EstadoPipeline {
  steps: PasoPipeline[];
  currentStep: number;
  isActive: boolean;
  totalProcessed: number;
  completedCount: number;
  deniedCount: number;
}

export interface CapaDefensa {
  id: number;
  name: string;
  description: string;
  status: string;
  icon: string;
  details: string;
}

export interface ReglaDenegacion {
  id: number;
  rule: string;
  description: string;
  niche: string;
  locked: boolean;
}

export interface EvidenciaHITL {
  requestId: string;
  title: string;
  description: string;
  status: string;
  priority: string;
  type: string;
  category: "safe" | "financial" | "destructive";
  requesterName: string;
  targetResource: string;
  targetAction: string;
  isReversible: boolean;
  createdAt: string;
  deadline: string | null;
  llmVerdict: boolean;
  evidenceFor: Array<{ point: string; weight: number; source: string }>;
  evidenceAgainst: Array<{ point: string; weight: number; source: string }>;
  decisions: Array<{
    decision: string;
    decisionByName: string;
    comment: string;
    decidedAt: string;
  }>;
  requiredApprovals: number;
  currentApprovals: number;
}

export interface DatosROI {
  valueToday: number;
  value7d: number;
  value30d: number;
  hoursSavedToday: number;
  hoursSaved7d: number;
  hoursSaved30d: number;
  actionsCompletedToday: number;
  actionsDeniedToday: number;
  securityBlocksTotal: number;
  totalAutomations: number;
  weeklyTrend: Array<{ day: string; exitosas: number; bloqueadas: number }>;
  planLimit: string;
}

export interface Nicho {
  id: string;
  name: string;
  icon: string;
  standard: string;
  standardName: string;
  active: boolean;
  rules: string[];
}

export interface ItemActividad {
  id: string;
  action: string;
  actorName: string;
  resource: string;
  resourceName: string;
  outcome: string;
  severity: string;
  createdAt: string;
}

/** Estado de salud de cada monitor SNA */
export interface EstadoMonitorSNA {
  tipo: "ligero" | "medio" | "pesado";
  etiqueta: string;
  valor: number; // 0–100
  estado: "optimo" | "normal" | "alerta" | "critico";
  detalle: string;
}

/** Información de feature gate para la UI */
export interface FeatureGateUI {
  feature: FeatureName;
  etiqueta: string;
  descripcion: string;
  tierMinimo: SubscriptionTierName;
  disponible: boolean;
}

/** Contexto de suscripción del usuario actual */
export interface ContextoSuscripcion {
  tier: SubscriptionTierName;
  nombreMostrar: string;
  limites: TierLimitsInfo;
  caracteristicas: FeatureGateUI[];
}

/** Plantilla generada por el agente Yamil para un nicho */
export interface PlantillaNicho {
  id: string;
  nombre: string;
  descripcion: string;
  tipo: string;
  nichoId: string;
  fechaCreacion: string;
  estado: "lista" | "borrador";
}

/** Archivo subido para procesamiento por Yamil */
export interface ArchivoSubido {
  nombre: string;
  tipo: string;
  tamaño: number;
  nichoId: string;
  estado: "recibido" | "procesando" | "completado" | "error";
  plantillaGenerada: string | null;
  fechaSubida: string;
}

/** Resultado de subida de archivo */
export interface ResultadoSubida {
  nombre: string;
  valido: boolean;
  razon?: string;
}

/** Item de navegación lateral */
export interface ItemNav {
  label: string;
  icon: React.ReactNode;
  subtexto?: string;
  badge?: string;
  badgeColor?: string;
  bloqueado?: boolean;
  tierRequerido?: string;
  children?: Array<{
    label: string;
    badge?: string;
    badgeColor?: string;
    bloqueado?: boolean;
    tierRequerido?: string;
  }>;
}
