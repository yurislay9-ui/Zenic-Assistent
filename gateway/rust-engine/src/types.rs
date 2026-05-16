// ─── Zenic-Agents v3 — Subscription Types (Rust, Compiled) ──────────────
// USDT TRC20 ONLY. No other payment references.
// Structs are Serde-serializable — exported via JSON string functions in lib.rs.

use serde::{Deserialize, Serialize};

// ═══════════════════════════════════════════════════════════════════════════
// Payment: USDT TRC20 Only — Manual/Semi-Manual Verification
// ═══════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum PaymentMethod {
    UsdtTrc20,
}

// Payment Verification Method — Manual/Semi-Manual Only
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum PaymentVerificationMethod {
    ManualAdmin,        // Admin manually confirms payment after checking wallet
    SemiManualOnChain,  // Semi-automated: system checks on-chain, admin approves
}

// Subscription creation must go through trial first
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SubscriptionCreationFlow {
    TrialFirst,  // ALL users must start with trial (mandatory)
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UsdtTrc20Payment {
    pub wallet_address: String,
    pub network: String,
    pub amount_usdt: f64,
    pub tx_hash: Option<String>,
    pub status: PaymentStatus,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum PaymentStatus {
    Pending,
    Confirming,
    Confirmed,
    Failed,
    Expired,
    Refunded,
}

// ═══════════════════════════════════════════════════════════════════════════
// Subscription Tiers: 5 Levels
// ═══════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum SubscriptionTier {
    Starter,
    Business,
    Enterprise,
    OnPremiseEnterprise,
    Trial,
}

impl SubscriptionTier {
    pub fn monthly_price_usdt(&self) -> f64 {
        match self {
            SubscriptionTier::Starter => 29.0,
            SubscriptionTier::Business => 99.0,
            SubscriptionTier::Enterprise => 299.0,
            SubscriptionTier::OnPremiseEnterprise => 799.0,
            SubscriptionTier::Trial => 0.0,
        }
    }

    pub fn setup_fee_usdt(&self) -> f64 {
        match self {
            SubscriptionTier::OnPremiseEnterprise => 2000.0,
            _ => 0.0,
        }
    }

    pub fn annual_price_usdt(&self) -> f64 {
        self.monthly_price_usdt() * 10.0
    }

    pub fn display_name(&self) -> &str {
        match self {
            SubscriptionTier::Starter => "Starter",
            SubscriptionTier::Business => "Business",
            SubscriptionTier::Enterprise => "Enterprise",
            SubscriptionTier::OnPremiseEnterprise => "On-Premise Enterprise",
            SubscriptionTier::Trial => "Trial (14 days)",
        }
    }

    pub fn recommended_for(&self) -> &str {
        match self {
            SubscriptionTier::Starter => "Equipos pequeños que inician con automatización",
            SubscriptionTier::Business => "Empresas en crecimiento con necesidades de compliance",
            SubscriptionTier::Enterprise => "Organizaciones grandes con requisitos estrictos de compliance",
            SubscriptionTier::OnPremiseEnterprise => "Organizaciones que requieren privacidad total y despliegue propio",
            SubscriptionTier::Trial => "Acceso completo al Plan Business por 14 días sin tarjeta",
        }
    }

    pub fn paid_tiers() -> Vec<SubscriptionTier> {
        vec![
            SubscriptionTier::Starter,
            SubscriptionTier::Business,
            SubscriptionTier::Enterprise,
            SubscriptionTier::OnPremiseEnterprise,
        ]
    }

    pub fn all_tiers() -> Vec<SubscriptionTier> {
        vec![
            SubscriptionTier::Starter,
            SubscriptionTier::Business,
            SubscriptionTier::Enterprise,
            SubscriptionTier::OnPremiseEnterprise,
            SubscriptionTier::Trial,
        ]
    }

    pub fn from_str_value(s: &str) -> Option<SubscriptionTier> {
        match s.to_lowercase().as_str() {
            "starter" => Some(SubscriptionTier::Starter),
            "business" => Some(SubscriptionTier::Business),
            "enterprise" => Some(SubscriptionTier::Enterprise),
            "on_premise_enterprise" | "onpremise" | "on-premise" => Some(SubscriptionTier::OnPremiseEnterprise),
            "trial" => Some(SubscriptionTier::Trial),
            _ => None,
        }
    }

    pub fn as_str(&self) -> &str {
        match self {
            SubscriptionTier::Starter => "starter",
            SubscriptionTier::Business => "business",
            SubscriptionTier::Enterprise => "enterprise",
            SubscriptionTier::OnPremiseEnterprise => "on_premise_enterprise",
            SubscriptionTier::Trial => "trial",
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Features
// ═══════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Feature {
    McpToolExecution, McpCustomTools, McpToolRegistration, McpRateLimiting,
    McpAuthApiKey, McpAuthOAuth2, McpAuthMTls, McpMerkleAudit,
    RbacBasicRoles, RbacCustomRoles, RbacDangerousPermApproval, RbacSsoIntegration,
    ObservabilityTracing, ObservabilityBusinessMetrics, ObservabilitySecurityMetrics,
    ObservabilityResilienceMetrics, ObservabilityOtelExport, ObservabilityJsonExport,
    ObservabilityCustomDashboards,
    PolicyDeclarativeYaml, PolicyVersioning, PolicyTesting, PolicyHotReload,
    PolicyComplianceMapping, PolicyComposition, PolicyConflictDetection,
    PolicyConstraintSolver, PolicySimulation, PolicyNamespaces, PolicyTemplates,
    PolicyApprovalWorkflow, PolicyImpactAnalysis, PolicyZ3Solver,
    PlaybookActivation, PlaybookCustomYaml, PlaybookRoiCalculator,
    PlaybookOnboardingWizard, PlaybookCertification, PlaybookComplianceMap,
    HitlApprovalWorkflow, HitlDelegation, HitlEscalation, HitlUndoReversible,
    HitlEvidence, HitlJustification, HitlSlaTracking, HitlAutoApprove,
    HitlExpiryAutoRevert,
    AuditBasicLog, AuditMerkleChain, AuditComplianceExport,
    ExecutorBasic, ExecutorData, ExecutorStorage, ExecutorSecurity,
    ExecutorAdvanced, ExecutorQueue, ExecutorMonitoring,
    OnPremiseDeployment, OnPremiseAirGap, OnPremiseCustomBranding, OnPremiseDataResidency,
}

pub fn feature_available(tier: SubscriptionTier, feature: Feature) -> bool {
    match feature {
        Feature::McpToolExecution => true,
        Feature::McpCustomTools => !matches!(tier, SubscriptionTier::Starter),
        Feature::McpToolRegistration => !matches!(tier, SubscriptionTier::Starter),
        Feature::McpRateLimiting => true,
        Feature::McpAuthApiKey => true,
        Feature::McpAuthOAuth2 => !matches!(tier, SubscriptionTier::Starter),
        Feature::McpAuthMTls => matches!(tier, SubscriptionTier::Enterprise | SubscriptionTier::OnPremiseEnterprise),
        Feature::McpMerkleAudit => true,
        Feature::RbacBasicRoles => true,
        Feature::RbacCustomRoles => !matches!(tier, SubscriptionTier::Starter),
        Feature::RbacDangerousPermApproval => !matches!(tier, SubscriptionTier::Starter),
        Feature::RbacSsoIntegration => matches!(tier, SubscriptionTier::Enterprise | SubscriptionTier::OnPremiseEnterprise),
        Feature::ObservabilityTracing => true,
        Feature::ObservabilityBusinessMetrics => true,
        Feature::ObservabilitySecurityMetrics => !matches!(tier, SubscriptionTier::Starter),
        Feature::ObservabilityResilienceMetrics => !matches!(tier, SubscriptionTier::Starter),
        Feature::ObservabilityOtelExport => !matches!(tier, SubscriptionTier::Starter),
        Feature::ObservabilityJsonExport => true,
        Feature::ObservabilityCustomDashboards => matches!(tier, SubscriptionTier::Enterprise | SubscriptionTier::OnPremiseEnterprise),
        Feature::PolicyDeclarativeYaml => true,
        Feature::PolicyVersioning => !matches!(tier, SubscriptionTier::Starter),
        Feature::PolicyTesting => !matches!(tier, SubscriptionTier::Starter),
        Feature::PolicyHotReload => !matches!(tier, SubscriptionTier::Starter),
        Feature::PolicyComplianceMapping => true,
        Feature::PolicyComposition => !matches!(tier, SubscriptionTier::Starter | SubscriptionTier::Business),
        Feature::PolicyConflictDetection => !matches!(tier, SubscriptionTier::Starter),
        Feature::PolicyConstraintSolver => !matches!(tier, SubscriptionTier::Starter),
        Feature::PolicySimulation => matches!(tier, SubscriptionTier::Enterprise | SubscriptionTier::OnPremiseEnterprise),
        Feature::PolicyNamespaces => !matches!(tier, SubscriptionTier::Starter),
        Feature::PolicyTemplates => !matches!(tier, SubscriptionTier::Starter),
        Feature::PolicyApprovalWorkflow => !matches!(tier, SubscriptionTier::Starter),
        Feature::PolicyImpactAnalysis => matches!(tier, SubscriptionTier::Enterprise | SubscriptionTier::OnPremiseEnterprise),
        Feature::PolicyZ3Solver => matches!(tier, SubscriptionTier::Enterprise | SubscriptionTier::OnPremiseEnterprise),
        Feature::PlaybookActivation => true,
        Feature::PlaybookCustomYaml => !matches!(tier, SubscriptionTier::Starter),
        Feature::PlaybookRoiCalculator => true,
        Feature::PlaybookOnboardingWizard => !matches!(tier, SubscriptionTier::Starter),
        Feature::PlaybookCertification => !matches!(tier, SubscriptionTier::Starter),
        Feature::PlaybookComplianceMap => true,
        Feature::HitlApprovalWorkflow => true,
        Feature::HitlDelegation => !matches!(tier, SubscriptionTier::Starter),
        Feature::HitlEscalation => !matches!(tier, SubscriptionTier::Starter),
        Feature::HitlUndoReversible => !matches!(tier, SubscriptionTier::Starter),
        Feature::HitlEvidence => !matches!(tier, SubscriptionTier::Starter),
        Feature::HitlJustification => !matches!(tier, SubscriptionTier::Starter),
        Feature::HitlSlaTracking => matches!(tier, SubscriptionTier::Enterprise | SubscriptionTier::OnPremiseEnterprise),
        Feature::HitlAutoApprove => !matches!(tier, SubscriptionTier::Starter),
        Feature::HitlExpiryAutoRevert => matches!(tier, SubscriptionTier::Enterprise | SubscriptionTier::OnPremiseEnterprise),
        Feature::AuditBasicLog => true,
        Feature::AuditMerkleChain => !matches!(tier, SubscriptionTier::Starter),
        Feature::AuditComplianceExport => !matches!(tier, SubscriptionTier::Starter),
        Feature::ExecutorBasic => true,
        Feature::ExecutorData => !matches!(tier, SubscriptionTier::Starter),
        Feature::ExecutorStorage => !matches!(tier, SubscriptionTier::Starter),
        Feature::ExecutorSecurity => !matches!(tier, SubscriptionTier::Starter),
        Feature::ExecutorAdvanced => matches!(tier, SubscriptionTier::Enterprise | SubscriptionTier::OnPremiseEnterprise),
        Feature::ExecutorQueue => !matches!(tier, SubscriptionTier::Starter),
        Feature::ExecutorMonitoring => !matches!(tier, SubscriptionTier::Starter),
        Feature::OnPremiseDeployment => matches!(tier, SubscriptionTier::OnPremiseEnterprise),
        Feature::OnPremiseAirGap => matches!(tier, SubscriptionTier::OnPremiseEnterprise),
        Feature::OnPremiseCustomBranding => matches!(tier, SubscriptionTier::OnPremiseEnterprise),
        Feature::OnPremiseDataResidency => matches!(tier, SubscriptionTier::OnPremiseEnterprise),
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Tier Limits
// ═══════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TierLimits {
    pub max_workflows: u32,
    pub max_actions_per_day: u32,
    pub max_policies: u32,
    pub max_team_members: u32,
    pub max_mcp_tools: u32,
    pub max_approval_requests_per_day: u32,
    pub max_playbooks: u32,
    pub max_namespaces: u32,
    pub max_simulations_per_month: u32,
    pub audit_retention_days: u32,
    pub trace_retention_days: u32,
    pub overage_rate_usdt: f64,
    pub sso_available: bool,
    pub on_premise_available: bool,
    pub custom_rbac: bool,
    pub z3_solver: bool,
}

impl TierLimits {
    pub fn starter() -> Self {
        TierLimits { max_workflows: 5, max_actions_per_day: 200, max_policies: 10, max_team_members: 3, max_mcp_tools: 10, max_approval_requests_per_day: 20, max_playbooks: 2, max_namespaces: 1, max_simulations_per_month: 5, audit_retention_days: 30, trace_retention_days: 7, overage_rate_usdt: 0.15, sso_available: false, on_premise_available: false, custom_rbac: false, z3_solver: false }
    }
    pub fn business() -> Self {
        TierLimits { max_workflows: 25, max_actions_per_day: 2000, max_policies: 50, max_team_members: 15, max_mcp_tools: 50, max_approval_requests_per_day: 200, max_playbooks: 8, max_namespaces: 5, max_simulations_per_month: 25, audit_retention_days: 90, trace_retention_days: 30, overage_rate_usdt: 0.10, sso_available: false, on_premise_available: false, custom_rbac: true, z3_solver: false }
    }
    pub fn enterprise() -> Self {
        TierLimits { max_workflows: 0, max_actions_per_day: 0, max_policies: 0, max_team_members: 0, max_mcp_tools: 0, max_approval_requests_per_day: 0, max_playbooks: 0, max_namespaces: 25, max_simulations_per_month: 0, audit_retention_days: 365, trace_retention_days: 90, overage_rate_usdt: 0.0, sso_available: true, on_premise_available: false, custom_rbac: true, z3_solver: true }
    }
    pub fn on_premise_enterprise() -> Self {
        TierLimits { max_workflows: 0, max_actions_per_day: 0, max_policies: 0, max_team_members: 0, max_mcp_tools: 0, max_approval_requests_per_day: 0, max_playbooks: 0, max_namespaces: 0, max_simulations_per_month: 0, audit_retention_days: 0, trace_retention_days: 0, overage_rate_usdt: 0.0, sso_available: true, on_premise_available: true, custom_rbac: true, z3_solver: true }
    }
    pub fn trial() -> Self { Self::business() }
    pub fn for_tier(tier: SubscriptionTier) -> Self {
        match tier {
            SubscriptionTier::Starter => Self::starter(),
            SubscriptionTier::Business => Self::business(),
            SubscriptionTier::Enterprise => Self::enterprise(),
            SubscriptionTier::OnPremiseEnterprise => Self::on_premise_enterprise(),
            SubscriptionTier::Trial => Self::trial(),
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Add-ons
// ═══════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum AddOn {
    ExtraWorkflowPack,
    ExtraTeamPack,
    CompliancePack,
    AdvancedAnalytics,
    PrioritySupport,
    Z3SolverAccess,
    ExtraSimulationsPack,
    AuditExtendedRetention,
}

impl AddOn {
    pub fn monthly_price_usdt(&self) -> f64 {
        match self {
            AddOn::ExtraWorkflowPack => 9.0, AddOn::ExtraTeamPack => 9.0,
            AddOn::CompliancePack => 29.0, AddOn::AdvancedAnalytics => 19.0,
            AddOn::PrioritySupport => 49.0, AddOn::Z3SolverAccess => 29.0,
            AddOn::ExtraSimulationsPack => 19.0, AddOn::AuditExtendedRetention => 19.0,
        }
    }
    pub fn display_name(&self) -> &str {
        match self {
            AddOn::ExtraWorkflowPack => "Pack +5 Workflows", AddOn::ExtraTeamPack => "Pack +5 Miembros",
            AddOn::CompliancePack => "Pack +10 Estándares Compliance", AddOn::AdvancedAnalytics => "Analytics Avanzados",
            AddOn::PrioritySupport => "Soporte Prioritario (SLA 4h)", AddOn::Z3SolverAccess => "Z3 Constraint Solver",
            AddOn::ExtraSimulationsPack => "Pack +50 Simulaciones", AddOn::AuditExtendedRetention => "Retención Extendida +365 días",
        }
    }
    pub fn available_for_tiers(&self) -> Vec<SubscriptionTier> {
        match self {
            AddOn::ExtraWorkflowPack => vec![SubscriptionTier::Starter, SubscriptionTier::Business],
            AddOn::ExtraTeamPack => vec![SubscriptionTier::Starter, SubscriptionTier::Business],
            AddOn::CompliancePack => vec![SubscriptionTier::Business, SubscriptionTier::Enterprise],
            AddOn::AdvancedAnalytics => vec![SubscriptionTier::Business, SubscriptionTier::Enterprise],
            AddOn::PrioritySupport => vec![SubscriptionTier::Business, SubscriptionTier::Enterprise],
            AddOn::Z3SolverAccess => vec![SubscriptionTier::Business],
            AddOn::ExtraSimulationsPack => vec![SubscriptionTier::Business],
            AddOn::AuditExtendedRetention => vec![SubscriptionTier::Starter, SubscriptionTier::Business],
        }
    }
    pub fn all() -> Vec<AddOn> {
        vec![AddOn::ExtraWorkflowPack, AddOn::ExtraTeamPack, AddOn::CompliancePack, AddOn::AdvancedAnalytics, AddOn::PrioritySupport, AddOn::Z3SolverAccess, AddOn::ExtraSimulationsPack, AddOn::AuditExtendedRetention]
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Trial
// ═══════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TrialConfig {
    pub duration_days: u32,
    pub requires_credit_card: bool,
    pub granted_tier: SubscriptionTier,
    pub max_trials_per_email: u32,
    pub auto_convert: bool,
    pub notification_schedule: Vec<u32>,
    pub mandatory_for_all: bool,         // true — everyone gets trial first
    pub trial_is_prerequisite: bool,     // true — cannot skip to paid without trial
}

impl Default for TrialConfig {
    fn default() -> Self {
        TrialConfig {
            duration_days: 14,
            requires_credit_card: false,
            granted_tier: SubscriptionTier::Business,
            max_trials_per_email: 1,
            auto_convert: false,
            notification_schedule: vec![3, 1, 0],
            mandatory_for_all: true,
            trial_is_prerequisite: true,
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Subscription Lifecycle
// ═══════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SubscriptionStatus {
    Trial, Active, PastDue, Cancelled, Expired, Suspended, PendingPayment,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Subscription {
    pub id: String,
    pub tenant_id: String,
    pub tier: SubscriptionTier,
    pub status: SubscriptionStatus,
    pub payment_method: PaymentMethod,
    pub billing_wallet: String,
    pub add_ons: Vec<AddOn>,
    pub started_at: String,
    pub current_period_end: String,
    pub trial_ends_at: Option<String>,
    pub auto_renew: bool,
    pub last_payment_tx_hash: Option<String>,
    pub cancelled_at: Option<String>,
    pub cancellation_reason: Option<String>,
}

// ═══════════════════════════════════════════════════════════════════════════
// Manual Payment Verification (USDT TRC20)
// ═══════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ManualPaymentVerification {
    pub payment_id: String,
    pub subscription_id: String,
    pub amount_usdt: f64,
    pub wallet_from: String,
    pub wallet_to: String,
    pub tx_hash: Option<String>,
    pub verification_method: PaymentVerificationMethod,
    pub status: ManualPaymentStatus,
    pub admin_notes: Option<String>,
    pub confirmed_by: Option<String>,
    pub confirmed_at: Option<String>,
    pub created_at: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ManualPaymentStatus {
    AwaitingPayment,       // User hasn't sent USDT yet
    AwaitingTxHash,       // Waiting for user to provide tx hash
    AwaitingConfirmation,  // tx hash provided, admin needs to confirm
    Confirmed,            // Admin confirmed payment
    Rejected,             // Admin rejected (insufficient amount, wrong wallet, etc.)
    Expired,              // Payment window expired
}

// ═══════════════════════════════════════════════════════════════════════════
// Pricing Calculation
// ═══════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PricingCalculation {
    pub tier: SubscriptionTier,
    pub monthly_price_usdt: f64,
    pub annual_price_usdt: f64,
    pub setup_fee_usdt: f64,
    pub add_ons_monthly_usdt: f64,
    pub total_first_month_usdt: f64,
    pub total_monthly_recurring_usdt: f64,
    pub total_annual_usdt: f64,
    pub overage_rate_usdt: f64,
    pub payment_currency: String,
    pub payment_network: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TierComparison {
    pub tiers: Vec<PricingCalculation>,
    pub recommended_tier: SubscriptionTier,
    pub recommendation_reason: String,
    pub payment_currency: String,
    pub payment_network: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UsageCheckResult {
    pub resource: String,
    pub allowed: bool,
    pub current_usage: u32,
    pub max_allowed: u32,
    pub remaining: u32,
    pub overage_charge_usdt: f64,
    pub minimum_tier: Option<String>,
    pub feature_available: bool,
    pub denial_reason: Option<String>,
}
