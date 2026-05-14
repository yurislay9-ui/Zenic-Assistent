//! Niche Catalog — Static compiled catalog of 24 cutting-edge niches.
//!
//! All niche definitions are compiled into the Rust binary at build time.
//! No YAML loading, no filesystem access, no runtime parsing. This
//! guarantees deterministic behavior and eliminates the GAP-1 blocker
//! (empty zenic-ffi) identified in the analysis.
//!
//! # Catalog Structure
//!
//! 7 categories, 24 niches total:
//!
//! | Category   | Count | Niches                                      |
//! |------------|-------|---------------------------------------------|
//! | IA y Datos | 4     | ai_automation, data_analytics, ml_operations, nlp_services |
//! | Tecnología Financiera | 4     | defi_protocols, neo_banking, insurtech, regtech |
//! | Tecnología de la Salud | 4     | telemedicine, mental_health_ai, genomics, wearables_health |
//! | Tecnología Verde | 3     | carbon_tracking, smart_grid, circular_economy |
//! | Tecnología Educativa | 3     | adaptive_learning, vr_education, micro_credentials |
//! | Tecnología Inmobiliaria | 3     | smart_buildings, digital_twins, fractional_ownership |
//! | Tecnología Jurídica | 3     | smart_contracts, legal_ai, compliance_automation |
//!
//! # PyO3 Functions
//!
//! - `catalog_get_all()` — list all NicheDefinitions
//! - `catalog_get_by_id(niche_id)` — lookup by niche_id
//! - `catalog_get_by_category(category)` — filter by category
//! - `catalog_search(query)` — search by name, domain, tags
//! - `catalog_count()` — total niches in catalog
//! - `catalog_ids()` — list all niche_id strings

use once_cell::sync::Lazy;
use pyo3::prelude::*;
use std::collections::HashMap;

use crate::niche::{
    DataSensitivity, FieldRequirement, NicheCategory, NicheDefinition,
    TemplateFieldSchema, TemplateFieldType, TemplateSection,
};

// ═══════════════════════════════════════════════════════════════
//  Static Catalog — compiled at build time
// ═══════════════════════════════════════════════════════════════

static CATALOG: Lazy<Vec<NicheDefinition>> = Lazy::new(|| {
    vec![
        // ── IA y Datos (4) ──────────────────────────────────────
        build_ai_automation(),
        build_data_analytics(),
        build_ml_operations(),
        build_nlp_services(),
        // ── Tecnología Financiera (4) ────────────────────────────────────────
        build_defi_protocols(),
        build_neo_banking(),
        build_insurtech(),
        build_regtech(),
        // ── Tecnología de la Salud (4) ─────────────────────────────────────
        build_telemedicine(),
        build_mental_health_ai(),
        build_genomics(),
        build_wearables_health(),
        // ── Tecnología Verde (3) ──────────────────────────────────────
        build_carbon_tracking(),
        build_smart_grid(),
        build_circular_economy(),
        // ── Tecnología Educativa (3) ─────────────────────────────────────────
        build_adaptive_learning(),
        build_vr_education(),
        build_micro_credentials(),
        // ── Tecnología Inmobiliaria (3) ───────────────────────────────────────
        build_smart_buildings(),
        build_digital_twins(),
        build_fractional_ownership(),
        // ── Tecnología Jurídica (3) ──────────────────────────────────────
        build_smart_contracts(),
        build_legal_ai(),
        build_compliance_automation(),
    ]
});

/// Index by niche_id for O(1) lookups.
static ID_INDEX: Lazy<HashMap<String, usize>> = Lazy::new(|| {
    let mut map = HashMap::new();
    for (i, niche) in CATALOG.iter().enumerate() {
        map.insert(niche.niche_id().to_string(), i);
    }
    map
});

// ═══════════════════════════════════════════════════════════════
//  PyO3 Catalog Functions
// ═══════════════════════════════════════════════════════════════

/// Get all niche definitions from the compiled catalog.
///
/// Returns a list of 24 NicheDefinition objects.
#[pyfunction]
pub fn catalog_get_all() -> Vec<NicheDefinition> {
    CATALOG.clone()
}

/// Get a niche definition by its niche_id.
///
/// Parameters
/// ----------
/// niche_id : str
///     The unique identifier of the niche (e.g. ``"telemedicine"``).
///
/// Returns
/// -------
/// NicheDefinition or None
///     The niche definition if found, None otherwise.
#[pyfunction]
pub fn catalog_get_by_id(niche_id: &str) -> Option<NicheDefinition> {
    ID_INDEX
        .get(niche_id)
        .map(|&idx| CATALOG[idx].clone())
}

/// Get all niche definitions in a given category.
///
/// Parameters
/// ----------
/// category : NicheCategory
///     The category to filter by.
///
/// Returns
/// -------
/// list[NicheDefinition]
///     All niches in the specified category.
#[pyfunction]
pub fn catalog_get_by_category(category: NicheCategory) -> Vec<NicheDefinition> {
    CATALOG
        .iter()
        .filter(|n| n.category() == category)
        .cloned()
        .collect()
}

/// Search niches by a text query.
///
/// Searches across name, domain, subdomain, and tags (case-insensitive).
/// Returns all niches where any field contains the query string.
///
/// Parameters
/// ----------
/// query : str
///     The search query string.
///
/// Returns
/// -------
/// list[NicheDefinition]
///     Matching niche definitions.
#[pyfunction]
pub fn catalog_search(query: &str) -> Vec<NicheDefinition> {
    let query_lower = query.to_lowercase();
    CATALOG
        .iter()
        .filter(|n| {
            // Buscar por niche_id, nombre, dominio, subdominio, categoría y tags
            n.niche_id().to_lowercase().contains(&query_lower)
                || n.name().to_lowercase().contains(&query_lower)
                || n.domain().to_lowercase().contains(&query_lower)
                || n.subdomain().to_lowercase().contains(&query_lower)
                || n.category().as_str().to_lowercase().contains(&query_lower)
                || n.tags().iter().any(|t| t.to_lowercase().contains(&query_lower))
        })
        .cloned()
        .collect()
}

/// Get the total number of niches in the catalog.
#[pyfunction]
pub fn catalog_count() -> usize {
    CATALOG.len()
}

/// Get all niche_id strings from the catalog.
#[pyfunction]
pub fn catalog_ids() -> Vec<String> {
    CATALOG.iter().map(|n| n.niche_id().to_string()).collect()
}

// ═══════════════════════════════════════════════════════════════
//  Niche Builders — one function per niche
// ═══════════════════════════════════════════════════════════════

// ── IA y Datos ────────────────────────────────────────────────

fn build_ai_automation() -> NicheDefinition {
    let mut n = NicheDefinition::new(
        "ai_automation".into(),
        "Automatización IA".into(),
        NicheCategory::AiData,
        "Plataforma de automatizacion inteligente con agentes AI para flujos de trabajo empresariales.".into(),
        "ai".into(),
        DataSensitivity::High,
    );
    n.set_subdomain("automation".into());
    n.set_scale("enterprise".into());
    n.set_tags(vec!["ai".into(), "automation".into(), "agents".into(), "workflows".into()]);
    n.set_required_documents(vec!["process_documentation".into(), "workflow_diagrams".into()]);
    n.set_compliance(vec!["GDPR".into(), "SOC2".into()]);
    n.add_section(section_business_identity());
    n.add_section(section_ai_model_config());
    n.add_section(section_workflow_automation());
    n.add_section(section_security_access());
    n
}

fn build_data_analytics() -> NicheDefinition {
    let mut n = NicheDefinition::new(
        "data_analytics".into(),
        "Análisis de Datos".into(),
        NicheCategory::AiData,
        "Plataforma de analisis de datos con dashboards interactivos, ETL automatizado y reportes predictivos.".into(),
        "data".into(),
        DataSensitivity::Medium,
    );
    n.set_subdomain("analytics".into());
    n.set_scale("large".into());
    n.set_tags(vec!["analytics".into(), "dashboards".into(), "etl".into(), "reports".into()]);
    n.set_required_documents(vec!["data_dictionary".into(), "report_specs".into()]);
    n.set_compliance(vec!["GDPR".into()]);
    n.add_section(section_business_identity());
    n.add_section(section_data_sources());
    n.add_section(section_analytics_config());
    n.add_section(section_security_access());
    n
}

fn build_ml_operations() -> NicheDefinition {
    let mut n = NicheDefinition::new(
        "ml_operations".into(),
        "Operaciones ML".into(),
        NicheCategory::AiData,
        "Plataforma MLOps para gestion del ciclo de vida de modelos ML: entrenamiento, despliegue, monitoreo y reentrenamiento.".into(),
        "ml".into(),
        DataSensitivity::High,
    );
    n.set_subdomain("mlops".into());
    n.set_scale("enterprise".into());
    n.set_tags(vec!["mlops".into(), "ml".into(), "deployment".into(), "monitoring".into()]);
    n.set_required_documents(vec!["model_documentation".into(), "training_data_spec".into()]);
    n.set_compliance(vec!["GDPR".into(), "SOC2".into()]);
    n.add_section(section_business_identity());
    n.add_section(section_ai_model_config());
    n.add_section(section_ml_pipeline());
    n.add_section(section_security_access());
    n
}

fn build_nlp_services() -> NicheDefinition {
    let mut n = NicheDefinition::new(
        "nlp_services".into(),
        "Servicios PLN".into(),
        NicheCategory::AiData,
        "Plataforma de procesamiento de lenguaje natural: chatbots, analisis de sentimiento, extraccion de entidades y traduccion.".into(),
        "nlp".into(),
        DataSensitivity::Medium,
    );
    n.set_subdomain("nlp".into());
    n.set_scale("large".into());
    n.set_tags(vec!["nlp".into(), "chatbot".into(), "sentiment".into(), "translation".into()]);
    n.set_required_documents(vec!["corpus_documentation".into(), "language_specs".into()]);
    n.set_compliance(vec!["GDPR".into()]);
    n.add_section(section_business_identity());
    n.add_section(section_nlp_config());
    n.add_section(section_security_access());
    n
}

// ── Tecnología Financiera ──────────────────────────────────────────

fn build_defi_protocols() -> NicheDefinition {
    let mut n = NicheDefinition::new(
        "defi_protocols".into(),
        "Protocolos DeFi".into(),
        NicheCategory::FinTech,
        "Plataforma DeFi para protocolos de finanzas descentralizadas: staking, lending, yield farming y gobernanza DAO.".into(),
        "defi".into(),
        DataSensitivity::Critical,
    );
    n.set_subdomain("defi".into());
    n.set_scale("enterprise".into());
    n.set_tags(vec!["defi".into(), "blockchain".into(), "staking".into(), "lending".into()]);
    n.set_required_documents(vec!["protocol_spec".into(), "audit_report".into(), "tokenomics".into()]);
    n.set_compliance(vec!["AML".into(), "KYC".into(), "SEC".into()]);
    n.add_section(section_business_identity());
    n.add_section(section_blockchain_config());
    n.add_section(section_financial_config());
    n.add_section(section_security_access());
    n
}

fn build_neo_banking() -> NicheDefinition {
    let mut n = NicheDefinition::new(
        "neo_banking".into(),
        "Banca Digital".into(),
        NicheCategory::FinTech,
        "Plataforma de banca digital con cuentas, transferencias, tarjetas virtuales y gestion de ahorros.".into(),
        "banking".into(),
        DataSensitivity::Critical,
    );
    n.set_subdomain("digital_banking".into());
    n.set_scale("enterprise".into());
    n.set_tags(vec!["banking".into(), "digital".into(), "payments".into(), "cards".into()]);
    n.set_required_documents(vec!["banking_license".into(), "compliance_docs".into()]);
    n.set_compliance(vec!["PCI-DSS".into(), "AML".into(), "KYC".into(), "SOX".into()]);
    n.add_section(section_business_identity());
    n.add_section(section_banking_config());
    n.add_section(section_financial_config());
    n.add_section(section_security_access());
    n
}

fn build_insurtech() -> NicheDefinition {
    let mut n = NicheDefinition::new(
        "insurtech".into(),
        "Tecnología Aseguradora".into(),
        NicheCategory::FinTech,
        "Plataforma de seguros digitales con suscripcion automatizada, evaluacion de riesgos AI y gestion de reclamos.".into(),
        "insurance".into(),
        DataSensitivity::Critical,
    );
    n.set_subdomain("insurance".into());
    n.set_scale("large".into());
    n.set_tags(vec!["insurance".into(), "claims".into(), "underwriting".into(), "risk".into()]);
    n.set_required_documents(vec!["insurance_product_spec".into(), "risk_model_docs".into()]);
    n.set_compliance(vec!["GDPR".into(), "Solvency II".into(), "AML".into()]);
    n.add_section(section_business_identity());
    n.add_section(section_insurance_config());
    n.add_section(section_financial_config());
    n.add_section(section_security_access());
    n
}

fn build_regtech() -> NicheDefinition {
    let mut n = NicheDefinition::new(
        "regtech".into(),
        "Tecnología Regulatoria".into(),
        NicheCategory::FinTech,
        "Plataforma de tecnologia regulatoria con monitoreo de cumplimiento automatizado, reportes regulatorios y gestion de riesgos.".into(),
        "regulatory".into(),
        DataSensitivity::Critical,
    );
    n.set_subdomain("compliance".into());
    n.set_scale("enterprise".into());
    n.set_tags(vec!["compliance".into(), "regulatory".into(), "reporting".into(), "risk".into()]);
    n.set_required_documents(vec!["regulation_requirements".into(), "compliance_checklist".into()]);
    n.set_compliance(vec!["GDPR".into(), "SOX".into(), "AML".into(), "Basel III".into()]);
    n.add_section(section_business_identity());
    n.add_section(section_regtech_config());
    n.add_section(section_security_access());
    n
}

// ── Tecnología de la Salud ───────────────────────────────────────

fn build_telemedicine() -> NicheDefinition {
    let mut n = NicheDefinition::new(
        "telemedicine".into(),
        "Telemedicina".into(),
        NicheCategory::HealthTech,
        "Plataforma de telemedicina para consultas virtuales con gestion de sesiones de video, notas medicas y cumplimiento HIPAA.".into(),
        "health".into(),
        DataSensitivity::Critical,
    );
    n.set_subdomain("virtual_care".into());
    n.set_scale("large".into());
    n.set_tags(vec!["telemedicine".into(), "video".into(), "health".into(), "hipaa".into()]);
    n.set_required_documents(vec!["medical_license".into(), "hipaa_compliance".into()]);
    n.set_compliance(vec!["HIPAA".into(), "GDPR".into()]);
    n.add_section(section_business_identity());
    n.add_section(section_patient_config());
    n.add_section(section_consultation_config());
    n.add_section(section_medical_compliance());
    n
}

fn build_mental_health_ai() -> NicheDefinition {
    let mut n = NicheDefinition::new(
        "mental_health_ai".into(),
        "IA de Salud Mental".into(),
        NicheCategory::HealthTech,
        "Plataforma de salud mental con AI para triaje, seguimiento de pacientes, sesiones de terapia asistidas y analisis de bienestar.".into(),
        "health".into(),
        DataSensitivity::Critical,
    );
    n.set_subdomain("mental_health".into());
    n.set_scale("large".into());
    n.set_tags(vec!["mental_health".into(), "therapy".into(), "ai".into(), "wellness".into()]);
    n.set_required_documents(vec!["clinical_protocols".into(), "ethics_approval".into()]);
    n.set_compliance(vec!["HIPAA".into(), "GDPR".into(), "APA".into()]);
    n.add_section(section_business_identity());
    n.add_section(section_patient_config());
    n.add_section(section_mental_health_config());
    n.add_section(section_medical_compliance());
    n
}

fn build_genomics() -> NicheDefinition {
    let mut n = NicheDefinition::new(
        "genomics".into(),
        "Genómica".into(),
        NicheCategory::HealthTech,
        "Plataforma de genómica con analisis de secuencias, variantes geneticas, farmacogenomica y reportes clinicos.".into(),
        "health".into(),
        DataSensitivity::Critical,
    );
    n.set_subdomain("genomics".into());
    n.set_scale("enterprise".into());
    n.set_tags(vec!["genomics".into(), "dna".into(), "sequencing".into(), "pharmacogenomics".into()]);
    n.set_required_documents(vec!["lab_certification".into(), "genetic_counseling_license".into()]);
    n.set_compliance(vec!["HIPAA".into(), "GINA".into(), "GDPR".into()]);
    n.add_section(section_business_identity());
    n.add_section(section_genomics_config());
    n.add_section(section_medical_compliance());
    n
}

fn build_wearables_health() -> NicheDefinition {
    let mut n = NicheDefinition::new(
        "wearables_health".into(),
        "Salud con Wearables".into(),
        NicheCategory::HealthTech,
        "Plataforma de salud con wearables para monitoreo de signos vitales, alertas preventivas y seguimiento de actividad fisica.".into(),
        "health".into(),
        DataSensitivity::High,
    );
    n.set_subdomain("wearables".into());
    n.set_scale("large".into());
    n.set_tags(vec!["wearables".into(), "vitals".into(), "fitness".into(), "monitoring".into()]);
    n.set_required_documents(vec!["device_specifications".into(), "medical_clearance".into()]);
    n.set_compliance(vec!["HIPAA".into(), "FDA".into(), "GDPR".into()]);
    n.add_section(section_business_identity());
    n.add_section(section_wearables_config());
    n.add_section(section_medical_compliance());
    n
}

// ── Tecnología Verde ────────────────────────────────────────

fn build_carbon_tracking() -> NicheDefinition {
    let mut n = NicheDefinition::new(
        "carbon_tracking".into(),
        "Seguimiento de Carbono".into(),
        NicheCategory::GreenTech,
        "Plataforma de seguimiento de huella de carbono con medicion, reportes ESG y compensacion de emisiones.".into(),
        "environment".into(),
        DataSensitivity::Medium,
    );
    n.set_subdomain("carbon".into());
    n.set_scale("large".into());
    n.set_tags(vec!["carbon".into(), "esg".into(), "emissions".into(), "sustainability".into()]);
    n.set_required_documents(vec!["emission_factors".into(), "esg_framework".into()]);
    n.set_compliance(vec!["GHG Protocol".into(), "TCFD".into()]);
    n.add_section(section_business_identity());
    n.add_section(section_carbon_config());
    n.add_section(section_security_access());
    n
}

fn build_smart_grid() -> NicheDefinition {
    let mut n = NicheDefinition::new(
        "smart_grid".into(),
        "Red Eléctrica Inteligente".into(),
        NicheCategory::GreenTech,
        "Plataforma de red electrica inteligente con monitoreo en tiempo real, distribucion automatizada y balance de carga.".into(),
        "energy".into(),
        DataSensitivity::High,
    );
    n.set_subdomain("smart_grid".into());
    n.set_scale("enterprise".into());
    n.set_tags(vec!["grid".into(), "energy".into(), "iot".into(), "distribution".into()]);
    n.set_required_documents(vec!["grid_topology".into(), "scada_specs".into()]);
    n.set_compliance(vec!["NERC".into(), "IEC 61850".into()]);
    n.add_section(section_business_identity());
    n.add_section(section_smart_grid_config());
    n.add_section(section_security_access());
    n
}

fn build_circular_economy() -> NicheDefinition {
    let mut n = NicheDefinition::new(
        "circular_economy".into(),
        "Economía Circular".into(),
        NicheCategory::GreenTech,
        "Plataforma de economia circular con trazabilidad de materiales, reciclaje inteligente y cadenas de reutilizacion.".into(),
        "environment".into(),
        DataSensitivity::Medium,
    );
    n.set_subdomain("circular".into());
    n.set_scale("large".into());
    n.set_tags(vec!["circular".into(), "recycling".into(), "sustainability".into(), "waste".into()]);
    n.set_required_documents(vec!["material_catalog".into(), "supply_chain_map".into()]);
    n.set_compliance(vec!["EU Circular Economy".into()]);
    n.add_section(section_business_identity());
    n.add_section(section_circular_config());
    n.add_section(section_security_access());
    n
}

// ── Tecnología Educativa ───────────────────────────────────────

fn build_adaptive_learning() -> NicheDefinition {
    let mut n = NicheDefinition::new(
        "adaptive_learning".into(),
        "Aprendizaje Adaptativo".into(),
        NicheCategory::EdTech,
        "Plataforma de aprendizaje adaptativo con rutas personalizadas, evaluacion inteligente y recomendaciones basadas en AI.".into(),
        "education".into(),
        DataSensitivity::Medium,
    );
    n.set_subdomain("adaptive".into());
    n.set_scale("large".into());
    n.set_tags(vec!["learning".into(), "adaptive".into(), "ai".into(), "education".into()]);
    n.set_required_documents(vec!["curriculum_docs".into(), "assessment_framework".into()]);
    n.set_compliance(vec!["FERPA".into(), "COPPA".into()]);
    n.add_section(section_business_identity());
    n.add_section(section_learning_config());
    n.add_section(section_security_access());
    n
}

fn build_vr_education() -> NicheDefinition {
    let mut n = NicheDefinition::new(
        "vr_education".into(),
        "Educación en RV".into(),
        NicheCategory::EdTech,
        "Plataforma educativa en realidad virtual con laboratorios inmersivos, simulaciones interactivas y sesiones colaborativas.".into(),
        "education".into(),
        DataSensitivity::Medium,
    );
    n.set_subdomain("vr".into());
    n.set_scale("large".into());
    n.set_tags(vec!["vr".into(), "immersive".into(), "simulation".into(), "education".into()]);
    n.set_required_documents(vec!["vr_content_spec".into(), "hardware_requirements".into()]);
    n.set_compliance(vec!["FERPA".into(), "COPPA".into()]);
    n.add_section(section_business_identity());
    n.add_section(section_vr_config());
    n.add_section(section_security_access());
    n
}

fn build_micro_credentials() -> NicheDefinition {
    let mut n = NicheDefinition::new(
        "micro_credentials".into(),
        "Microcredenciales".into(),
        NicheCategory::EdTech,
        "Plataforma de micro-credenciales con certificaciones digitales verificables, badges blockchain y rutas de habilidades.".into(),
        "education".into(),
        DataSensitivity::Medium,
    );
    n.set_subdomain("credentials".into());
    n.set_scale("medium".into());
    n.set_tags(vec!["credentials".into(), "badges".into(), "blockchain".into(), "skills".into()]);
    n.set_required_documents(vec!["credential_framework".into(), "skills_taxonomy".into()]);
    n.set_compliance(vec!["FERPA".into()]);
    n.add_section(section_business_identity());
    n.add_section(section_credentials_config());
    n.add_section(section_security_access());
    n
}

// ── Tecnología Inmobiliaria ─────────────────────────────────────────

fn build_smart_buildings() -> NicheDefinition {
    let mut n = NicheDefinition::new(
        "smart_buildings".into(),
        "Edificios Inteligentes".into(),
        NicheCategory::PropTech,
        "Plataforma de edificios inteligentes con IoT, gestion energetica automatizada, control de acceso y mantenimiento predictivo.".into(),
        "realestate".into(),
        DataSensitivity::High,
    );
    n.set_subdomain("smart_building".into());
    n.set_scale("large".into());
    n.set_tags(vec!["iot".into(), "building".into(), "energy".into(), "access".into()]);
    n.set_required_documents(vec!["building_plans".into(), "iot_device_catalog".into()]);
    n.set_compliance(vec!["BREEAM".into(), "LEED".into()]);
    n.add_section(section_business_identity());
    n.add_section(section_smart_building_config());
    n.add_section(section_security_access());
    n
}

fn build_digital_twins() -> NicheDefinition {
    let mut n = NicheDefinition::new(
        "digital_twins".into(),
        "Gemelos Digitales".into(),
        NicheCategory::PropTech,
        "Plataforma de gemelos digitales para simulacion de propiedades, analisis de rendimiento y planificacion de mantenimiento.".into(),
        "realestate".into(),
        DataSensitivity::High,
    );
    n.set_subdomain("digital_twin".into());
    n.set_scale("enterprise".into());
    n.set_tags(vec!["digital_twin".into(), "simulation".into(), "3d".into(), "bim".into()]);
    n.set_required_documents(vec!["bim_models".into(), "sensor_data_spec".into()]);
    n.set_compliance(vec!["ISO 23247".into()]);
    n.add_section(section_business_identity());
    n.add_section(section_digital_twin_config());
    n.add_section(section_security_access());
    n
}

fn build_fractional_ownership() -> NicheDefinition {
    let mut n = NicheDefinition::new(
        "fractional_ownership".into(),
        "Propiedad Fraccional".into(),
        NicheCategory::PropTech,
        "Plataforma de propiedad fraccional con tokenizacion de activos, gestion de copropiedad y distribucion de rendimientos.".into(),
        "realestate".into(),
        DataSensitivity::Critical,
    );
    n.set_subdomain("fractional".into());
    n.set_scale("large".into());
    n.set_tags(vec!["fractional".into(), "tokenization".into(), "blockchain".into(), "realestate".into()]);
    n.set_required_documents(vec!["property_legal_docs".into(), "tokenomics".into()]);
    n.set_compliance(vec!["SEC".into(), "AML".into(), "KYC".into()]);
    n.add_section(section_business_identity());
    n.add_section(section_fractional_config());
    n.add_section(section_security_access());
    n
}

// ── Tecnología Jurídica ────────────────────────────────────────

fn build_smart_contracts() -> NicheDefinition {
    let mut n = NicheDefinition::new(
        "smart_contracts".into(),
        "Contratos Inteligentes".into(),
        NicheCategory::LegalTech,
        "Plataforma de contratos inteligentes con generacion automatizada, auditoria de codigo, despliegue en blockchain y monitoreo.".into(),
        "legal".into(),
        DataSensitivity::Critical,
    );
    n.set_subdomain("smart_contract".into());
    n.set_scale("enterprise".into());
    n.set_tags(vec!["smart_contract".into(), "blockchain".into(), "solidity".into(), "audit".into()]);
    n.set_required_documents(vec!["contract_templates".into(), "audit_requirements".into()]);
    n.set_compliance(vec!["SEC".into(), "eIDAS".into()]);
    n.add_section(section_business_identity());
    n.add_section(section_smart_contract_config());
    n.add_section(section_security_access());
    n
}

fn build_legal_ai() -> NicheDefinition {
    let mut n = NicheDefinition::new(
        "legal_ai".into(),
        "IA Jurídica".into(),
        NicheCategory::LegalTech,
        "Plataforma de AI legal con analisis de documentos, revision de contratos, investigacion juridica y predicion de resultados.".into(),
        "legal".into(),
        DataSensitivity::Critical,
    );
    n.set_subdomain("legal_ai".into());
    n.set_scale("large".into());
    n.set_tags(vec!["legal".into(), "ai".into(), "contracts".into(), "research".into()]);
    n.set_required_documents(vec!["legal_document_samples".into(), "jurisdiction_specs".into()]);
    n.set_compliance(vec!["GDPR".into(), "ABA".into(), "SOX".into()]);
    n.add_section(section_business_identity());
    n.add_section(section_legal_ai_config());
    n.add_section(section_security_access());
    n
}

fn build_compliance_automation() -> NicheDefinition {
    let mut n = NicheDefinition::new(
        "compliance_automation".into(),
        "Automatización de Cumplimiento".into(),
        NicheCategory::LegalTech,
        "Plataforma de automatizacion de cumplimiento con monitoreo continuo, evaluacion de riesgos, reportes automaticos y auditoria.".into(),
        "legal".into(),
        DataSensitivity::Critical,
    );
    n.set_subdomain("compliance".into());
    n.set_scale("enterprise".into());
    n.set_tags(vec!["compliance".into(), "automation".into(), "audit".into(), "risk".into()]);
    n.set_required_documents(vec!["compliance_framework".into(), "audit_schedule".into()]);
    n.set_compliance(vec!["SOX".into(), "GDPR".into(), "ISO 27001".into()]);
    n.add_section(section_business_identity());
    n.add_section(section_compliance_auto_config());
    n.add_section(section_security_access());
    n
}

// ═══════════════════════════════════════════════════════════════
//  Reusable Section Builders
// ═══════════════════════════════════════════════════════════════

/// Common "Business Identity" section — present in ALL niches.
fn section_business_identity() -> TemplateSection {
    let mut s = TemplateSection::new(
        "business_identity".into(),
        "Business Identity".into(),
    );
    s.set_description("Core business identification and branding.".into());
    s.set_order(1);
    s.add_field(field("business_name", "Business Name", TemplateFieldType::Text, FieldRequirement::Required));
    s.add_field(field("business_type", "Business Type", TemplateFieldType::Enum, FieldRequirement::Required));
    s.add_field(field("tax_id", "Tax ID / RUC", TemplateFieldType::Text, FieldRequirement::Required));
    s.add_field(field("country", "Country", TemplateFieldType::Text, FieldRequirement::Required));
    s.add_field(field("industry", "Industry", TemplateFieldType::Text, FieldRequirement::Required));
    s.add_field(field("website", "Website", TemplateFieldType::Url, FieldRequirement::Optional));
    s.add_field(field("logo_url", "Logo URL", TemplateFieldType::Url, FieldRequirement::Optional));
    s
}

/// Common "Security & Access" section — present in ALL niches.
fn section_security_access() -> TemplateSection {
    let mut s = TemplateSection::new(
        "security_access".into(),
        "Security & Access".into(),
    );
    s.set_description("Authentication, authorization and security configuration.".into());
    s.set_order(99);
    s.add_field(field("auth_method", "Authentication Method", TemplateFieldType::Enum, FieldRequirement::Required));
    s.add_field(field("admin_email", "Admin Email", TemplateFieldType::Email, FieldRequirement::Required));
    s.add_field(field("admin_phone", "Admin Phone", TemplateFieldType::Phone, FieldRequirement::Optional));
    s.add_field(field("enable_2fa", "Enable 2FA", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s.add_field(field("session_timeout_minutes", "Session Timeout (minutes)", TemplateFieldType::Number, FieldRequirement::Optional));
    s
}

/// AI Model Configuration section.
fn section_ai_model_config() -> TemplateSection {
    let mut s = TemplateSection::new(
        "ai_model_config".into(),
        "AI Model Configuration".into(),
    );
    s.set_description("Configuration for AI/ML models used in automation.".into());
    s.set_order(2);
    s.add_field(field("model_provider", "Model Provider", TemplateFieldType::Enum, FieldRequirement::Required));
    s.add_field(field("model_name", "Model Name", TemplateFieldType::Text, FieldRequirement::Required));
    s.add_field(field("temperature", "Temperature", TemplateFieldType::Number, FieldRequirement::Optional));
    s.add_field(field("max_tokens", "Max Tokens", TemplateFieldType::Number, FieldRequirement::Optional));
    s.add_field(field("api_key_ref", "API Key Reference", TemplateFieldType::Text, FieldRequirement::Required));
    s.add_field(field("fallback_model", "Fallback Model", TemplateFieldType::Text, FieldRequirement::Optional));
    s
}

/// Workflow Automation section.
fn section_workflow_automation() -> TemplateSection {
    let mut s = TemplateSection::new(
        "workflow_automation".into(),
        "Workflow Automation".into(),
    );
    s.set_description("Automated workflow definitions and triggers.".into());
    s.set_order(3);
    s.add_field(field("workflow_name", "Workflow Name", TemplateFieldType::Text, FieldRequirement::Required));
    s.add_field(field("trigger_type", "Trigger Type", TemplateFieldType::Enum, FieldRequirement::Required));
    s.add_field(field("steps_count", "Number of Steps", TemplateFieldType::Number, FieldRequirement::Required));
    s.add_field(field("error_handling", "Error Handling Strategy", TemplateFieldType::Enum, FieldRequirement::Optional));
    s.add_field(field("notification_on_complete", "Notify on Completion", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s
}

/// Data Sources section.
fn section_data_sources() -> TemplateSection {
    let mut s = TemplateSection::new(
        "data_sources".into(),
        "Data Sources".into(),
    );
    s.set_description("External data source connections and configuration.".into());
    s.set_order(2);
    s.add_field(field("source_type", "Source Type", TemplateFieldType::Enum, FieldRequirement::Required));
    s.add_field(field("connection_string", "Connection String", TemplateFieldType::Text, FieldRequirement::Required));
    s.add_field(field("sync_interval", "Sync Interval (seconds)", TemplateFieldType::Number, FieldRequirement::Optional));
    s.add_field(field("data_format", "Data Format", TemplateFieldType::Enum, FieldRequirement::Required));
    s
}

/// Analytics Configuration section.
fn section_analytics_config() -> TemplateSection {
    let mut s = TemplateSection::new(
        "analytics_config".into(),
        "Analytics Configuration".into(),
    );
    s.set_description("Dashboard and reporting configuration.".into());
    s.set_order(3);
    s.add_field(field("dashboard_name", "Dashboard Name", TemplateFieldType::Text, FieldRequirement::Required));
    s.add_field(field("refresh_interval", "Refresh Interval (seconds)", TemplateFieldType::Number, FieldRequirement::Optional));
    s.add_field(field("export_format", "Export Format", TemplateFieldType::Enum, FieldRequirement::Optional));
    s.add_field(field("enable_predictions", "Enable Predictions", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s
}

/// ML Pipeline section.
fn section_ml_pipeline() -> TemplateSection {
    let mut s = TemplateSection::new(
        "ml_pipeline".into(),
        "ML Pipeline".into(),
    );
    s.set_description("Machine learning pipeline configuration for training and deployment.".into());
    s.set_order(3);
    s.add_field(field("pipeline_name", "Pipeline Name", TemplateFieldType::Text, FieldRequirement::Required));
    s.add_field(field("training_data_source", "Training Data Source", TemplateFieldType::Text, FieldRequirement::Required));
    s.add_field(field("validation_split", "Validation Split %", TemplateFieldType::Percentage, FieldRequirement::Optional));
    s.add_field(field("auto_retrain", "Auto Retrain", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s.add_field(field("retrain_interval_hours", "Retrain Interval (hours)", TemplateFieldType::Number, FieldRequirement::Optional));
    s
}

/// NLP Configuration section.
fn section_nlp_config() -> TemplateSection {
    let mut s = TemplateSection::new(
        "nlp_config".into(),
        "NLP Configuration".into(),
    );
    s.set_description("Natural language processing service configuration.".into());
    s.set_order(2);
    s.add_field(field("primary_language", "Primary Language", TemplateFieldType::Text, FieldRequirement::Required));
    s.add_field(field("supported_languages", "Supported Languages", TemplateFieldType::Json, FieldRequirement::Optional));
    s.add_field(field("enable_sentiment", "Enable Sentiment Analysis", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s.add_field(field("enable_ner", "Enable Named Entity Recognition", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s.add_field(field("chatbot_name", "Chatbot Name", TemplateFieldType::Text, FieldRequirement::Optional));
    s
}

/// Blockchain Configuration section.
fn section_blockchain_config() -> TemplateSection {
    let mut s = TemplateSection::new(
        "blockchain_config".into(),
        "Blockchain Configuration".into(),
    );
    s.set_description("Blockchain network and smart contract configuration.".into());
    s.set_order(2);
    s.add_field(field("network", "Blockchain Network", TemplateFieldType::Enum, FieldRequirement::Required));
    s.add_field(field("contract_address", "Contract Address", TemplateFieldType::Text, FieldRequirement::Required));
    s.add_field(field("gas_limit", "Gas Limit", TemplateFieldType::Number, FieldRequirement::Optional));
    s.add_field(field("wallet_private_key_ref", "Wallet Key Reference", TemplateFieldType::Text, FieldRequirement::Required));
    s
}

/// Financial Configuration section.
fn section_financial_config() -> TemplateSection {
    let mut s = TemplateSection::new(
        "financial_config".into(),
        "Financial Configuration".into(),
    );
    s.set_description("Currency, pricing, and payment configuration.".into());
    s.set_order(3);
    s.add_field(field("base_currency", "Base Currency", TemplateFieldType::Currency, FieldRequirement::Required));
    s.add_field(field("payment_gateway", "Payment Gateway", TemplateFieldType::Enum, FieldRequirement::Required));
    s.add_field(field("tax_rate", "Tax Rate %", TemplateFieldType::Percentage, FieldRequirement::Optional));
    s.add_field(field("enable_invoicing", "Enable Invoicing", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s
}

/// Banking Configuration section.
fn section_banking_config() -> TemplateSection {
    let mut s = TemplateSection::new(
        "banking_config".into(),
        "Banking Configuration".into(),
    );
    s.set_description("Core banking features and account management.".into());
    s.set_order(2);
    s.add_field(field("account_types", "Account Types", TemplateFieldType::Json, FieldRequirement::Required));
    s.add_field(field("enable_virtual_cards", "Enable Virtual Cards", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s.add_field(field("daily_transfer_limit", "Daily Transfer Limit", TemplateFieldType::Currency, FieldRequirement::Required));
    s.add_field(field("enable_savings_goals", "Enable Savings Goals", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s
}

/// Insurance Configuration section.
fn section_insurance_config() -> TemplateSection {
    let mut s = TemplateSection::new(
        "insurance_config".into(),
        "Insurance Configuration".into(),
    );
    s.set_description("Insurance product and underwriting configuration.".into());
    s.set_order(2);
    s.add_field(field("product_type", "Insurance Product Type", TemplateFieldType::Enum, FieldRequirement::Required));
    s.add_field(field("coverage_amount", "Default Coverage Amount", TemplateFieldType::Currency, FieldRequirement::Required));
    s.add_field(field("enable_ai_underwriting", "Enable AI Underwriting", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s.add_field(field("claims_auto_approval_limit", "Auto-Approval Limit", TemplateFieldType::Currency, FieldRequirement::Optional));
    s
}

/// RegTech Configuration section.
fn section_regtech_config() -> TemplateSection {
    let mut s = TemplateSection::new(
        "regtech_config".into(),
        "RegTech Configuration".into(),
    );
    s.set_description("Regulatory compliance monitoring configuration.".into());
    s.set_order(2);
    s.add_field(field("regulations", "Applicable Regulations", TemplateFieldType::Json, FieldRequirement::Required));
    s.add_field(field("monitoring_frequency", "Monitoring Frequency", TemplateFieldType::Enum, FieldRequirement::Required));
    s.add_field(field("enable_auto_reporting", "Enable Auto Reporting", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s.add_field(field("alert_threshold", "Alert Threshold", TemplateFieldType::Percentage, FieldRequirement::Optional));
    s
}

/// Patient Configuration section (HealthTech).
fn section_patient_config() -> TemplateSection {
    let mut s = TemplateSection::new(
        "patient_config".into(),
        "Patient Configuration".into(),
    );
    s.set_description("Patient management and registration configuration.".into());
    s.set_order(2);
    s.add_field(field("require_insurance", "Require Insurance", TemplateFieldType::Boolean, FieldRequirement::Required));
    s.add_field(field("patient_id_format", "Patient ID Format", TemplateFieldType::Enum, FieldRequirement::Required));
    s.add_field(field("enable_patient_portal", "Enable Patient Portal", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s.add_field(field("emergency_contact_required", "Emergency Contact Required", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s
}

/// Consultation Configuration section (Telemedicine).
fn section_consultation_config() -> TemplateSection {
    let mut s = TemplateSection::new(
        "consultation_config".into(),
        "Consultation Configuration".into(),
    );
    s.set_description("Virtual consultation settings and video session configuration.".into());
    s.set_order(3);
    s.add_field(field("default_duration_minutes", "Default Duration (minutes)", TemplateFieldType::Number, FieldRequirement::Required));
    s.add_field(field("enable_recording", "Enable Recording", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s.add_field(field("max_participants", "Max Participants", TemplateFieldType::Number, FieldRequirement::Optional));
    s.add_field(field("consultation_fee", "Consultation Fee", TemplateFieldType::Currency, FieldRequirement::Optional));
    s
}

/// Medical Compliance section (HealthTech).
fn section_medical_compliance() -> TemplateSection {
    let mut s = TemplateSection::new(
        "medical_compliance".into(),
        "Medical Compliance".into(),
    );
    s.set_description("Healthcare compliance and data protection configuration.".into());
    s.set_order(4);
    s.add_field(field("data_encryption_level", "Data Encryption Level", TemplateFieldType::Enum, FieldRequirement::Required));
    s.add_field(field("audit_retention_days", "Audit Retention (days)", TemplateFieldType::Number, FieldRequirement::Required));
    s.add_field(field("enable_consent_management", "Enable Consent Management", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s.add_field(field("data_backup_frequency", "Backup Frequency", TemplateFieldType::Enum, FieldRequirement::Required));
    s
}

/// Mental Health Configuration section.
fn section_mental_health_config() -> TemplateSection {
    let mut s = TemplateSection::new(
        "mental_health_config".into(),
        "Mental Health Configuration".into(),
    );
    s.set_description("Mental health-specific AI triage and session settings.".into());
    s.set_order(3);
    s.add_field(field("triage_model", "Triage Model", TemplateFieldType::Enum, FieldRequirement::Required));
    s.add_field(field("crisis_protocol", "Crisis Protocol", TemplateFieldType::Text, FieldRequirement::Required));
    s.add_field(field("session_duration_minutes", "Session Duration (minutes)", TemplateFieldType::Number, FieldRequirement::Required));
    s.add_field(field("enable_mood_tracking", "Enable Mood Tracking", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s
}

/// Genomics Configuration section.
fn section_genomics_config() -> TemplateSection {
    let mut s = TemplateSection::new(
        "genomics_config".into(),
        "Genomics Configuration".into(),
    );
    s.set_description("Genomic analysis and variant interpretation configuration.".into());
    s.set_order(2);
    s.add_field(field("sequencing_platform", "Sequencing Platform", TemplateFieldType::Enum, FieldRequirement::Required));
    s.add_field(field("reference_genome", "Reference Genome", TemplateFieldType::Text, FieldRequirement::Required));
    s.add_field(field("enable_pharmacogenomics", "Enable Pharmacogenomics", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s.add_field(field("variant_calling_method", "Variant Calling Method", TemplateFieldType::Enum, FieldRequirement::Required));
    s
}

/// Wearables Configuration section.
fn section_wearables_config() -> TemplateSection {
    let mut s = TemplateSection::new(
        "wearables_config".into(),
        "Wearables Configuration".into(),
    );
    s.set_description("Wearable device integration and health monitoring configuration.".into());
    s.set_order(2);
    s.add_field(field("supported_devices", "Supported Devices", TemplateFieldType::Json, FieldRequirement::Required));
    s.add_field(field("vital_signs_monitored", "Vital Signs Monitored", TemplateFieldType::Json, FieldRequirement::Required));
    s.add_field(field("alert_threshold_config", "Alert Thresholds", TemplateFieldType::Json, FieldRequirement::Optional));
    s.add_field(field("data_sync_interval", "Data Sync Interval (seconds)", TemplateFieldType::Number, FieldRequirement::Optional));
    s
}

/// Carbon Configuration section.
fn section_carbon_config() -> TemplateSection {
    let mut s = TemplateSection::new(
        "carbon_config".into(),
        "Carbon Configuration".into(),
    );
    s.set_description("Carbon footprint measurement and ESG reporting configuration.".into());
    s.set_order(2);
    s.add_field(field("emission_scopes", "Emission Scopes", TemplateFieldType::Json, FieldRequirement::Required));
    s.add_field(field("reporting_framework", "Reporting Framework", TemplateFieldType::Enum, FieldRequirement::Required));
    s.add_field(field("enable_offset_tracking", "Enable Offset Tracking", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s.add_field(field("measurement_frequency", "Measurement Frequency", TemplateFieldType::Enum, FieldRequirement::Required));
    s
}

/// Smart Grid Configuration section.
fn section_smart_grid_config() -> TemplateSection {
    let mut s = TemplateSection::new(
        "smart_grid_config".into(),
        "Smart Grid Configuration".into(),
    );
    s.set_description("Smart grid monitoring and distribution configuration.".into());
    s.set_order(2);
    s.add_field(field("grid_type", "Grid Type", TemplateFieldType::Enum, FieldRequirement::Required));
    s.add_field(field("meter_count", "Number of Meters", TemplateFieldType::Number, FieldRequirement::Required));
    s.add_field(field("enable_demand_response", "Enable Demand Response", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s.add_field(field("scada_integration", "SCADA Integration", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s
}

/// Circular Economy Configuration section.
fn section_circular_config() -> TemplateSection {
    let mut s = TemplateSection::new(
        "circular_config".into(),
        "Circular Economy Configuration".into(),
    );
    s.set_description("Material tracking and recycling process configuration.".into());
    s.set_order(2);
    s.add_field(field("material_categories", "Material Categories", TemplateFieldType::Json, FieldRequirement::Required));
    s.add_field(field("tracking_method", "Tracking Method", TemplateFieldType::Enum, FieldRequirement::Required));
    s.add_field(field("enable_recycling_marketplace", "Enable Recycling Marketplace", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s.add_field(field("certification_required", "Certification Required", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s
}

/// Learning Configuration section.
fn section_learning_config() -> TemplateSection {
    let mut s = TemplateSection::new(
        "learning_config".into(),
        "Learning Configuration".into(),
    );
    s.set_description("Adaptive learning paths and assessment configuration.".into());
    s.set_order(2);
    s.add_field(field("learning_style_model", "Learning Style Model", TemplateFieldType::Enum, FieldRequirement::Required));
    s.add_field(field("assessment_types", "Assessment Types", TemplateFieldType::Json, FieldRequirement::Required));
    s.add_field(field("enable_ai_recommendations", "Enable AI Recommendations", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s.add_field(field("progress_tracking", "Progress Tracking", TemplateFieldType::Enum, FieldRequirement::Required));
    s
}

/// VR Configuration section.
fn section_vr_config() -> TemplateSection {
    let mut s = TemplateSection::new(
        "vr_config".into(),
        "VR Configuration".into(),
    );
    s.set_description("Virtual reality environment and content configuration.".into());
    s.set_order(2);
    s.add_field(field("vr_platform", "VR Platform", TemplateFieldType::Enum, FieldRequirement::Required));
    s.add_field(field("max_concurrent_users", "Max Concurrent Users", TemplateFieldType::Number, FieldRequirement::Required));
    s.add_field(field("enable_haptic_feedback", "Enable Haptic Feedback", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s.add_field(field("session_duration_limit", "Session Duration Limit (minutes)", TemplateFieldType::Number, FieldRequirement::Optional));
    s
}

/// Credentials Configuration section.
fn section_credentials_config() -> TemplateSection {
    let mut s = TemplateSection::new(
        "credentials_config".into(),
        "Credentials Configuration".into(),
    );
    s.set_description("Digital credential and badge configuration.".into());
    s.set_order(2);
    s.add_field(field("credential_format", "Credential Format", TemplateFieldType::Enum, FieldRequirement::Required));
    s.add_field(field("enable_blockchain_verification", "Enable Blockchain Verification", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s.add_field(field("issuer_name", "Issuer Name", TemplateFieldType::Text, FieldRequirement::Required));
    s.add_field(field("validity_period_days", "Validity Period (days)", TemplateFieldType::Number, FieldRequirement::Optional));
    s
}

/// Smart Building Configuration section.
fn section_smart_building_config() -> TemplateSection {
    let mut s = TemplateSection::new(
        "smart_building_config".into(),
        "Smart Building Configuration".into(),
    );
    s.set_description("IoT device and building automation configuration.".into());
    s.set_order(2);
    s.add_field(field("building_type", "Building Type", TemplateFieldType::Enum, FieldRequirement::Required));
    s.add_field(field("iot_device_count", "IoT Device Count", TemplateFieldType::Number, FieldRequirement::Required));
    s.add_field(field("enable_energy_management", "Enable Energy Management", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s.add_field(field("access_control_type", "Access Control Type", TemplateFieldType::Enum, FieldRequirement::Required));
    s
}

/// Digital Twin Configuration section.
fn section_digital_twin_config() -> TemplateSection {
    let mut s = TemplateSection::new(
        "digital_twin_config".into(),
        "Digital Twin Configuration".into(),
    );
    s.set_description("Digital twin simulation and sensor configuration.".into());
    s.set_order(2);
    s.add_field(field("twin_type", "Twin Type", TemplateFieldType::Enum, FieldRequirement::Required));
    s.add_field(field("simulation_fidelity", "Simulation Fidelity", TemplateFieldType::Enum, FieldRequirement::Required));
    s.add_field(field("sensor_count", "Sensor Count", TemplateFieldType::Number, FieldRequirement::Required));
    s.add_field(field("real_time_sync", "Real-time Sync", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s
}

/// Fractional Ownership Configuration section.
fn section_fractional_config() -> TemplateSection {
    let mut s = TemplateSection::new(
        "fractional_config".into(),
        "Fractional Ownership Configuration".into(),
    );
    s.set_description("Property tokenization and co-ownership configuration.".into());
    s.set_order(2);
    s.add_field(field("tokenization_standard", "Tokenization Standard", TemplateFieldType::Enum, FieldRequirement::Required));
    s.add_field(field("min_investment", "Minimum Investment", TemplateFieldType::Currency, FieldRequirement::Required));
    s.add_field(field("enable_dividend_distribution", "Enable Dividend Distribution", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s.add_field(field("kyc_required", "KYC Required", TemplateFieldType::Boolean, FieldRequirement::Required));
    s
}

/// Smart Contract Configuration section.
fn section_smart_contract_config() -> TemplateSection {
    let mut s = TemplateSection::new(
        "smart_contract_config".into(),
        "Smart Contract Configuration".into(),
    );
    s.set_description("Smart contract generation and deployment configuration.".into());
    s.set_order(2);
    s.add_field(field("contract_language", "Contract Language", TemplateFieldType::Enum, FieldRequirement::Required));
    s.add_field(field("target_network", "Target Network", TemplateFieldType::Enum, FieldRequirement::Required));
    s.add_field(field("enable_auto_audit", "Enable Auto Audit", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s.add_field(field("upgradeable_contract", "Upgradeable Contract", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s
}

/// Legal AI Configuration section.
fn section_legal_ai_config() -> TemplateSection {
    let mut s = TemplateSection::new(
        "legal_ai_config".into(),
        "Legal AI Configuration".into(),
    );
    s.set_description("Legal document analysis and AI research configuration.".into());
    s.set_order(2);
    s.add_field(field("jurisdiction", "Primary Jurisdiction", TemplateFieldType::Text, FieldRequirement::Required));
    s.add_field(field("document_types", "Document Types", TemplateFieldType::Json, FieldRequirement::Required));
    s.add_field(field("enable_contract_review", "Enable Contract Review", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s.add_field(field("enable_outcome_prediction", "Enable Outcome Prediction", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s
}

/// Compliance Automation Configuration section.
fn section_compliance_auto_config() -> TemplateSection {
    let mut s = TemplateSection::new(
        "compliance_auto_config".into(),
        "Compliance Automation Configuration".into(),
    );
    s.set_description("Automated compliance monitoring and reporting configuration.".into());
    s.set_order(2);
    s.add_field(field("compliance_frameworks", "Compliance Frameworks", TemplateFieldType::Json, FieldRequirement::Required));
    s.add_field(field("monitoring_scope", "Monitoring Scope", TemplateFieldType::Enum, FieldRequirement::Required));
    s.add_field(field("enable_auto_remediation", "Enable Auto Remediation", TemplateFieldType::Boolean, FieldRequirement::Optional));
    s.add_field(field("report_frequency", "Report Frequency", TemplateFieldType::Enum, FieldRequirement::Required));
    s
}

// ═══════════════════════════════════════════════════════════════
//  Field Builder Helper
// ═══════════════════════════════════════════════════════════════

/// Shorthand to create a TemplateFieldSchema.
fn field(
    name: &str,
    display_name: &str,
    field_type: TemplateFieldType,
    requirement: FieldRequirement,
) -> TemplateFieldSchema {
    TemplateFieldSchema::new(
        name.to_string(),
        display_name.to_string(),
        field_type,
        requirement,
    )
}

// ═══════════════════════════════════════════════════════════════
//  Unit Tests
// ═══════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_catalog_has_24_niches() {
        assert_eq!(CATALOG.len(), 24);
    }

    #[test]
    fn test_catalog_id_index_complete() {
        assert_eq!(ID_INDEX.len(), 24);
    }

    #[test]
    fn test_catalog_get_by_id() {
        let niche = catalog_get_by_id("telemedicine").expect("telemedicine should exist");
        assert_eq!(niche.name(), "Telemedicina");
        assert_eq!(niche.category(), NicheCategory::HealthTech);
        assert_eq!(niche.data_sensitivity(), DataSensitivity::Critical);
    }

    #[test]
    fn test_catalog_get_by_id_not_found() {
        assert!(catalog_get_by_id("nonexistent_niche").is_none());
    }

    #[test]
    fn test_catalog_get_by_category_ai_data() {
        let niches = catalog_get_by_category(NicheCategory::AiData);
        assert_eq!(niches.len(), 4);
    }

    #[test]
    fn test_catalog_get_by_category_fintech() {
        let niches = catalog_get_by_category(NicheCategory::FinTech);
        assert_eq!(niches.len(), 4);
    }

    #[test]
    fn test_catalog_get_by_category_healthtech() {
        let niches = catalog_get_by_category(NicheCategory::HealthTech);
        assert_eq!(niches.len(), 4);
    }

    #[test]
    fn test_catalog_get_by_category_greentech() {
        let niches = catalog_get_by_category(NicheCategory::GreenTech);
        assert_eq!(niches.len(), 3);
    }

    #[test]
    fn test_catalog_get_by_category_edtech() {
        let niches = catalog_get_by_category(NicheCategory::EdTech);
        assert_eq!(niches.len(), 3);
    }

    #[test]
    fn test_catalog_get_by_category_proptech() {
        let niches = catalog_get_by_category(NicheCategory::PropTech);
        assert_eq!(niches.len(), 3);
    }

    #[test]
    fn test_catalog_get_by_category_legaltech() {
        let niches = catalog_get_by_category(NicheCategory::LegalTech);
        assert_eq!(niches.len(), 3);
    }

    #[test]
    fn test_catalog_search() {
        let results = catalog_search("health");
        assert!(!results.is_empty());
        // Should match telemedicine, mental_health_ai, wearables_health
        assert!(results.iter().any(|n| n.niche_id() == "telemedicine"));
    }

    #[test]
    fn test_catalog_search_case_insensitive() {
        let results = catalog_search("BANKING");
        assert!(!results.is_empty());
        assert!(results.iter().any(|n| n.niche_id() == "neo_banking"));
    }

    #[test]
    fn test_catalog_count() {
        assert_eq!(catalog_count(), 24);
    }

    #[test]
    fn test_catalog_ids() {
        let ids = catalog_ids();
        assert_eq!(ids.len(), 24);
        assert!(ids.contains(&"telemedicine".to_string()));
        assert!(ids.contains(&"ai_automation".to_string()));
        assert!(ids.contains(&"defi_protocols".to_string()));
    }

    #[test]
    fn test_all_niches_have_business_identity() {
        for niche in CATALOG.iter() {
            let section = niche.get_section("business_identity");
            assert!(
                section.is_some(),
                "Niche {} missing business_identity section",
                niche.niche_id(),
            );
        }
    }

    #[test]
    fn test_all_niches_have_security_access() {
        for niche in CATALOG.iter() {
            let section = niche.get_section("security_access");
            assert!(
                section.is_some(),
                "Niche {} missing security_access section",
                niche.niche_id(),
            );
        }
    }

    #[test]
    fn test_all_niches_have_required_fields() {
        for niche in CATALOG.iter() {
            assert!(
                niche.required_fields() > 0,
                "Niche {} has no required fields",
                niche.niche_id(),
            );
        }
    }

    #[test]
    fn test_all_niches_have_compliance() {
        for niche in CATALOG.iter() {
            assert!(
                !niche.compliance().is_empty(),
                "Niche {} has no compliance standards",
                niche.niche_id(),
            );
        }
    }

    #[test]
    fn test_all_niche_ids_are_unique() {
        let mut seen = std::collections::HashSet::new();
        for niche in CATALOG.iter() {
            assert!(
                seen.insert(niche.niche_id().to_string()),
                "Duplicate niche_id: {}",
                niche.niche_id(),
            );
        }
    }

    #[test]
    fn test_critical_niches_have_high_sensitivity() {
        let critical_ids = ["telemedicine", "mental_health_ai", "genomics",
                           "defi_protocols", "neo_banking", "insurtech",
                           "fractional_ownership", "smart_contracts"];
        for id in &critical_ids {
            let niche = catalog_get_by_id(id).expect(id);
            assert!(
                matches!(niche.data_sensitivity(), DataSensitivity::Critical),
                "Niche {} should be Critical sensitivity, got {:?}",
                id, niche.data_sensitivity(),
            );
        }
    }
}
