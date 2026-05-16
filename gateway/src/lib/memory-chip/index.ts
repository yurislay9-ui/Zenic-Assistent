/**
 * Zenic-Agents Memory Chip Client
 *
 * TypeScript client for the Chip de Memoria Adaptativa Binaria.
 * Connects to the Rust backend via the PyO3 bridge.
 * Provides types, constants, and a client class for API route consumption.
 */

// ─── Types ────────────────────────────────────────────────────────────────

export interface SemanticMapping {
  mapping_id: string;
  origin: string;
  relation: string;
  destination: string;
  mechanism: MechanismType;
  confidence: number;
  tenant_id: string;
  created_at: number;
  approved: boolean;
  merkle_hash: string | null;
}

export type MechanismType =
  | 'schema_drift'
  | 'intent_routing'
  | 'policy_refinement'
  | 'ontology_base';

export const MECHANISM_TYPES: MechanismType[] = [
  'schema_drift',
  'intent_routing',
  'policy_refinement',
  'ontology_base',
];

export function isValidMechanism(value: string): value is MechanismType {
  return MECHANISM_TYPES.includes(value as MechanismType);
}

export interface MemoryApprovalPayload {
  admin_evidence_review: boolean;
  admin_justification: string;
  risk_acknowledgment: boolean;
  admin_session_id: string;
  mapping_id: string;
  ia_question: string;
  ia_response: boolean;
  evidence_for: string[];
  evidence_against: string[];
  consensus_score: number;
}

export interface LookupResult {
  cache_hit: boolean;
  mapping: SemanticMapping | null;
  origin: string;
  destination: string;
}

export interface AdaptResult {
  adapted: boolean;
  corrected_field: string | null;
  mapping_id: string | null;
}

export interface MemoryChipStats {
  total_mappings: number;
  approved_mappings: number;
  pending_mappings: number;
  cache_hit_rate: number;
  mechanisms: Record<string, number>;
  lru_size: number;
  lru_capacity: number;
}

export interface SubscriptionFeatures {
  mechanisms_allowed: string[];
  max_mappings_per_month: number;
  lru_cache_size: number;
  ontology_access: boolean;
  export_import: boolean;
}

export const SUBSCRIPTION_TIERS = {
  starter: {
    name: 'Starter',
    mechanisms: ['schema_drift'],
    max_mappings: 10,
    lru_size: 100,
    ontology: false,
    export_import: false,
  },
  business: {
    name: 'Business',
    mechanisms: ['schema_drift', 'intent_routing'],
    max_mappings: 50,
    lru_size: 500,
    ontology: false,
    export_import: false,
  },
  enterprise: {
    name: 'Enterprise',
    mechanisms: ['schema_drift', 'intent_routing', 'policy_refinement'],
    max_mappings: -1, // unlimited
    lru_size: 2000,
    ontology: true,
    export_import: false,
  },
  on_premise: {
    name: 'On-Premise',
    mechanisms: ['schema_drift', 'intent_routing', 'policy_refinement', 'ontology_base'],
    max_mappings: -1, // unlimited
    lru_size: -1, // unlimited
    ontology: true,
    export_import: true,
  },
} as const;

export type SubscriptionTier = keyof typeof SUBSCRIPTION_TIERS;

export const VALID_TIERS: SubscriptionTier[] = [
  'starter',
  'business',
  'enterprise',
  'on_premise',
];

export function isValidTier(value: string): value is SubscriptionTier {
  return VALID_TIERS.includes(value as SubscriptionTier);
}

export function getSubscriptionFeatures(tier: SubscriptionTier): SubscriptionFeatures {
  const config = SUBSCRIPTION_TIERS[tier];
  return {
    mechanisms_allowed: [...config.mechanisms],
    max_mappings_per_month: config.max_mappings,
    lru_cache_size: config.lru_size,
    ontology_access: config.ontology,
    export_import: config.export_import,
  };
}

export interface OntologySearchResult {
  term: string;
  mapped_to: string;
  category: string;
  confidence: number;
}

export interface LifecycleEpisode {
  episode_id: string;
  mapping: SemanticMapping;
  current_phase: LifecyclePhase;
  created_at: number;
  updated_at: number;
}

export type LifecyclePhase =
  | 'observe'
  | 'hypothesize'
  | 'validate'
  | 'approve'
  | 'deploy'
  | 'retire';

export const LIFECYCLE_PHASES: LifecyclePhase[] = [
  'observe',
  'hypothesize',
  'validate',
  'approve',
  'deploy',
  'retire',
];

export function isValidLifecyclePhase(value: string): value is LifecyclePhase {
  return LIFECYCLE_PHASES.includes(value as LifecyclePhase);
}

/**
 * Get the next valid phase transitions for a given current phase.
 * Enforces the linear lifecycle: observe → hypothesize → validate → approve → deploy → retire
 */
export function getNextPhases(currentPhase: LifecyclePhase): LifecyclePhase[] {
  const idx = LIFECYCLE_PHASES.indexOf(currentPhase);
  if (idx === -1 || idx === LIFECYCLE_PHASES.length - 1) return [];
  return LIFECYCLE_PHASES.slice(idx + 1);
}

// ─── Ontology Base (built-in Spanish business terms) ──────────────────

interface OntologyEntry {
  term: string;
  mapped_to: string;
  category: string;
  confidence: number;
}

const ONTOLOGY_BASE: OntologyEntry[] = [
  { term: 'cliente', mapped_to: 'customer', category: 'business', confidence: 0.99 },
  { term: 'factura', mapped_to: 'invoice', category: 'finance', confidence: 0.99 },
  { term: 'pago', mapped_to: 'payment', category: 'finance', confidence: 0.99 },
  { term: 'cuenta', mapped_to: 'account', category: 'finance', confidence: 0.98 },
  { term: 'cancelar', mapped_to: 'cancel', category: 'action', confidence: 0.97 },
  { term: 'suspendido', mapped_to: 'suspended', category: 'status', confidence: 0.98 },
  { term: 'activo', mapped_to: 'active', category: 'status', confidence: 0.99 },
  { term: 'pendiente', mapped_to: 'pending', category: 'status', confidence: 0.98 },
  { term: 'reparación', mapped_to: 'repair', category: 'service', confidence: 0.95 },
  { term: 'urgente', mapped_to: 'urgent', category: 'priority', confidence: 0.96 },
  { term: 'crítico', mapped_to: 'critical', category: 'priority', confidence: 0.95 },
  { term: 'gasto', mapped_to: 'expense', category: 'finance', confidence: 0.97 },
  { term: 'ingreso', mapped_to: 'income', category: 'finance', confidence: 0.97 },
  { term: 'empleado', mapped_to: 'employee', category: 'hr', confidence: 0.99 },
  { term: 'departamento', mapped_to: 'department', category: 'organization', confidence: 0.98 },
  { term: 'producto', mapped_to: 'product', category: 'business', confidence: 0.99 },
  { term: 'servicio', mapped_to: 'service', category: 'business', confidence: 0.99 },
  { term: 'contrato', mapped_to: 'contract', category: 'legal', confidence: 0.98 },
  { term: 'política', mapped_to: 'policy', category: 'governance', confidence: 0.96 },
  { term: 'estatus', mapped_to: 'status', category: 'metadata', confidence: 0.94 },
  { term: 'tumba', mapped_to: 'cancel', category: 'slang_action', confidence: 0.80 },
  { term: 'estatus_cliente', mapped_to: 'estado_id', category: 'schema_drift', confidence: 0.85 },
  { term: 'reparación urgente', mapped_to: 'gasto_crítico', category: 'policy_refinement', confidence: 0.82 },
  { term: 'tumba la cuenta', mapped_to: 'cancelar_suscripcion', category: 'intent_routing', confidence: 0.78 },
  { term: 'monto', mapped_to: 'amount', category: 'finance', confidence: 0.97 },
  { term: 'fecha', mapped_to: 'date', category: 'metadata', confidence: 0.99 },
  { term: 'nombre', mapped_to: 'name', category: 'metadata', confidence: 0.99 },
  { term: 'dirección', mapped_to: 'address', category: 'metadata', confidence: 0.98 },
  { term: 'teléfono', mapped_to: 'phone', category: 'contact', confidence: 0.99 },
  { term: 'correo', mapped_to: 'email', category: 'contact', confidence: 0.98 },
  { term: 'empresa', mapped_to: 'company', category: 'business', confidence: 0.99 },
  { term: 'proveedor', mapped_to: 'vendor', category: 'business', confidence: 0.97 },
  { term: 'inventario', mapped_to: 'inventory', category: 'operations', confidence: 0.98 },
  { term: 'pedido', mapped_to: 'order', category: 'commerce', confidence: 0.99 },
  { term: 'envío', mapped_to: 'shipment', category: 'logistics', confidence: 0.97 },
  { term: 'devolución', mapped_to: 'return', category: 'commerce', confidence: 0.96 },
  { term: 'reembolso', mapped_to: 'refund', category: 'finance', confidence: 0.97 },
  { term: 'descuento', mapped_to: 'discount', category: 'finance', confidence: 0.98 },
  { term: 'impuesto', mapped_to: 'tax', category: 'finance', confidence: 0.99 },
  { term: 'subtotal', mapped_to: 'subtotal', category: 'finance', confidence: 0.99 },
  { term: 'total', mapped_to: 'total', category: 'finance', confidence: 0.99 },
  { term: 'saldo', mapped_to: 'balance', category: 'finance', confidence: 0.97 },
  { term: 'deuda', mapped_to: 'debt', category: 'finance', confidence: 0.96 },
  { term: 'crédito', mapped_to: 'credit', category: 'finance', confidence: 0.96 },
  { term: 'débito', mapped_to: 'debit', category: 'finance', confidence: 0.96 },
  { term: 'auditoría', mapped_to: 'audit', category: 'governance', confidence: 0.98 },
  { term: 'cumplimiento', mapped_to: 'compliance', category: 'governance', confidence: 0.97 },
  { term: 'riesgo', mapped_to: 'risk', category: 'governance', confidence: 0.98 },
  { term: 'seguridad', mapped_to: 'security', category: 'governance', confidence: 0.99 },
  { term: 'privacidad', mapped_to: 'privacy', category: 'governance', confidence: 0.97 },
];

/**
 * Search the ontology base for matching terms.
 * Returns results where the term contains the search string (case-insensitive).
 */
export function searchOntologyBase(term: string): OntologySearchResult[] {
  const normalizedTerm = term.toLowerCase().trim();
  if (!normalizedTerm) return [];

  return ONTOLOGY_BASE.filter(
    (entry) =>
      entry.term.toLowerCase().includes(normalizedTerm) ||
      entry.mapped_to.toLowerCase().includes(normalizedTerm),
  ).map((entry) => ({
    term: entry.term,
    mapped_to: entry.mapped_to,
    category: entry.category,
    confidence: entry.confidence,
  }));
}

// ─── Merkle Hash (simplified BLAKE3-like for TypeScript) ──────────────

/**
 * Generate a simple hash for a mapping.
 * In production, this would use the Rust BLAKE3 implementation.
 */
export async function generateMappingHash(data: string): Promise<string> {
  const encoder = new TextEncoder();
  const dataBuffer = encoder.encode(data);
  const hashBuffer = await crypto.subtle.digest('SHA-256', dataBuffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
}

// ─── Client Class ─────────────────────────────────────────────────────

export class MemoryChipClient {
  private baseUrl: string;

  constructor(baseUrl: string = '/api/v1/memory-chip') {
    this.baseUrl = baseUrl;
  }

  /** Lookup a semantic mapping by text */
  async lookup(text: string, tenantId: string = '__anonymous__'): Promise<LookupResult> {
    const res = await fetch(`${this.baseUrl}/lookup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, tenant_id: tenantId }),
    });
    if (!res.ok) throw new Error(`Lookup failed: ${res.statusText}`);
    return res.json();
  }

  /** Try to adapt a failed field using learned mappings */
  async tryAdapt(failedField: string, tenantId: string = '__anonymous__'): Promise<AdaptResult> {
    const res = await fetch(`${this.baseUrl}/adapt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ failed_field: failedField, tenant_id: tenantId }),
    });
    if (!res.ok) throw new Error(`Adapt failed: ${res.statusText}`);
    return res.json();
  }

  /** Insert a new semantic mapping */
  async insertMapping(
    origin: string,
    relation: string,
    destination: string,
    mechanism: string,
    tenantId: string = '__anonymous__',
  ): Promise<{ mapping_id: string }> {
    const res = await fetch(`${this.baseUrl}/mappings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ origin, relation, destination, mechanism, tenant_id: tenantId }),
    });
    if (!res.ok) throw new Error(`Insert failed: ${res.statusText}`);
    return res.json();
  }

  /** Approve a mapping with HITL mandatory fields */
  async approveMapping(
    mappingId: string,
    payload: Omit<MemoryApprovalPayload, 'mapping_id'>,
  ): Promise<{ success: boolean; merkle_hash?: string; yaml_rendered?: boolean }> {
    const res = await fetch(`${this.baseUrl}/mappings/${mappingId}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...payload, mapping_id: mappingId }),
    });
    if (!res.ok) throw new Error(`Approve failed: ${res.statusText}`);
    return res.json();
  }

  /** Get chip statistics */
  async stats(tenantId: string = '__anonymous__'): Promise<MemoryChipStats> {
    const res = await fetch(`${this.baseUrl}/stats?tenant_id=${tenantId}`);
    if (!res.ok) throw new Error(`Stats failed: ${res.statusText}`);
    return res.json();
  }

  /** Search the ontology base for a term */
  async searchOntology(term: string): Promise<OntologySearchResult[]> {
    const res = await fetch(`${this.baseUrl}/ontology/search?term=${encodeURIComponent(term)}`);
    if (!res.ok) throw new Error(`Ontology search failed: ${res.statusText}`);
    return res.json();
  }

  /** Get subscription features for a tier */
  async subscriptionFeatures(tier: SubscriptionTier): Promise<SubscriptionFeatures> {
    const res = await fetch(`${this.baseUrl}/subscription/features?tier=${tier}`);
    if (!res.ok) throw new Error(`Features failed: ${res.statusText}`);
    return res.json();
  }

  /** Start a learning lifecycle episode */
  async startEpisode(
    origin: string,
    relation: string,
    destination: string,
    mechanism: string,
    tenantId: string = '__anonymous__',
  ): Promise<LifecycleEpisode> {
    const res = await fetch(`${this.baseUrl}/lifecycle/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ origin, relation, destination, mechanism, tenant_id: tenantId }),
    });
    if (!res.ok) throw new Error(`Start episode failed: ${res.statusText}`);
    return res.json();
  }

  /** Advance a lifecycle episode to the next phase */
  async advanceEpisode(episodeId: string, phase: string): Promise<{ success: boolean }> {
    const res = await fetch(`${this.baseUrl}/lifecycle/advance`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ episode_id: episodeId, phase }),
    });
    if (!res.ok) throw new Error(`Advance episode failed: ${res.statusText}`);
    return res.json();
  }
}
