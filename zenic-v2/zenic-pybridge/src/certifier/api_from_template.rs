use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::config::*;
use super::helpers::*;
use super::result::*;
use super::schema_types::*;
use super::types::*;

// ═══════════════════════════════════════════════════════════════
//  PyO3 Functions — certifier_from_template
// ═══════════════════════════════════════════════════════════════

/// Create a BlueprintConfig from a completed template dict.
///
/// Extracts all filled field values from the template and organizes
/// them into a structured BlueprintConfig ready for certification.
///
/// Parameters
/// ----------
/// template_dict : dict
///     The completed template dict (from completer_finalize or
///     template_generate with filled values).
///
/// Returns
/// -------
/// CertificationResult
///     Result with the BlueprintConfig in the `config` field.
///     Check `success` to verify extraction was successful.
#[pyfunction]
pub fn certifier_from_template(
    template_dict: &Bound<'_, PyDict>,
    py: Python<'_>,
) -> PyResult<CertificationResult> {
    let mut warnings: Vec<String> = Vec::new();
    let mut errors: Vec<String> = Vec::new();

    // Validate template structure
    let template_obj = match template_dict.get_item("template") {
        Ok(Some(t)) => t,
        _ => {
            return Ok(CertificationResult {
                success: false,
                blueprint: None,
                config: None,
                status: CertificationStatus::Error,
                content_hash: String::new(),
                elapsed_ms: 0,
                warnings,
                errors: vec!["Missing 'template' key in template_dict".to_string()],
            });
        }
    };

    let template_pydict: &Bound<'_, PyDict> = match template_obj.downcast() {
        Ok(d) => d,
        _ => {
            return Ok(CertificationResult {
                success: false,
                blueprint: None,
                config: None,
                status: CertificationStatus::Error,
                content_hash: String::new(),
                elapsed_ms: 0,
                warnings,
                errors: vec!["'template' is not a dict".to_string()],
            });
        }
    };

    // Validate completeness using template_validate
    let validation = crate::template::template_validate(template_dict, py)?;
    let is_valid: bool = validation
        .get_item("valid")
        .ok()
        .flatten()
        .and_then(|v| v.extract().ok())
        .unwrap_or(false);

    let missing_required: usize = validation
        .get_item("missing_required")
        .ok()
        .flatten()
        .and_then(|v| v.extract().ok())
        .unwrap_or(0);

    if !is_valid {
        warnings.push(format!(
            "Template has {} missing required fields. Blueprint may be incomplete.",
            missing_required,
        ));
    }

    // Extract metadata
    let niche_id = get_template_metadata_str(template_dict, "niche_id");
    let domain = get_template_metadata_str(template_dict, "domain");
    let subdomain = get_template_metadata_str(template_dict, "subdomain");
    let data_sensitivity = get_template_metadata_str(template_dict, "data_sensitivity");
    let compliance = get_template_compliance(template_dict);

    // Extract business identity fields
    let business_name = get_template_field_value(template_dict, "business_identity", "business_name")
        .unwrap_or_else(|| "Unknown Business".to_string());
    let business_type = get_template_field_value(template_dict, "business_identity", "business_type")
        .unwrap_or_else(|| "unknown".to_string());

    // Build config
    let mut config = BlueprintConfig::new(
        niche_id,
        business_name,
        business_type,
        domain,
        data_sensitivity,
    );
    config.subdomain = subdomain;

    // Add compliance standards
    for standard in &compliance {
        if let Err(e) = config.add_compliance(standard.clone()) {
            warnings.push(e.to_string());
        }
    }

    // Extract all field values as settings
    let settings = extract_settings_from_template(template_dict);
    for (key, value) in &settings {
        config.set_setting(key.clone(), value.clone());
    }

    // Add default monitors based on data sensitivity
    let default_monitors = build_default_monitors(&config.data_sensitivity);
    for monitor in default_monitors {
        if let Err(e) = config.add_monitor(monitor) {
            warnings.push(e.to_string());
        }
    }

    // Add default actions based on niche type
    let default_actions = build_default_actions(&config.niche_id, &config.data_sensitivity);
    for action in default_actions {
        if let Err(e) = config.add_action(action) {
            warnings.push(e.to_string());
        }
    }

    // Add default database schema
    let default_tables = build_default_db_schema(&config.niche_id);
    for table in default_tables {
        if let Err(e) = config.add_db_table(table) {
            warnings.push(e.to_string());
        }
    }

    // Add tags from metadata
    let tags: Vec<String> = template_pydict
        .get_item("metadata")
        .ok()
        .flatten()
        .and_then(|m| m.downcast::<PyDict>().ok())
        .and_then(|m| m.get_item("tags").ok().flatten())
        .and_then(|v| v.extract().ok())
        .unwrap_or_default();
    for tag in tags {
        config.add_tag(tag);
    }

    if !config.is_certifiable() {
        errors.push("BlueprintConfig is not certifiable: missing required fields (niche_id, business_name, domain, data_sensitivity)".to_string());
    }

    let success = errors.is_empty();
    let status = if success {
        CertificationStatus::Draft
    } else {
        CertificationStatus::Error
    };

    Ok(CertificationResult {
        success,
        blueprint: None,
        config: Some(config),
        status,
        content_hash: String::new(),
        elapsed_ms: 0,
        warnings,
        errors,
    })
}

// ═══════════════════════════════════════════════════════════════
//  Default Builders — auto-generate monitors, actions, db_schema
// ═══════════════════════════════════════════════════════════════

/// Build default monitors based on data sensitivity level.
pub(super) fn build_default_monitors(data_sensitivity: &str) -> Vec<MonitorDef> {
    let mut monitors: Vec<MonitorDef> = Vec::new();

    // Always add health check monitor
    let mut health = MonitorDef::new(
        "health_check".to_string(),
        "liviano".to_string(),
        "System Health Check".to_string(),
    );
    health.set_description("Basic system health and uptime monitoring".to_string());
    health.set_interval(60);
    monitors.push(health);

    // Data sensitivity based monitors
    match data_sensitivity {
        "low" => {
            let mut usage = MonitorDef::new(
                "resource_usage".to_string(),
                "liviano".to_string(),
                "Resource Usage".to_string(),
            );
            usage.set_description("CPU and memory usage monitoring".to_string());
            usage.set_interval(300);
            monitors.push(usage);
        }
        "medium" => {
            let mut usage = MonitorDef::new(
                "resource_usage".to_string(),
                "liviano".to_string(),
                "Resource Usage".to_string(),
            );
            usage.set_description("CPU and memory usage monitoring".to_string());
            usage.set_interval(120);
            monitors.push(usage);

            let mut error_rate = MonitorDef::new(
                "error_rate".to_string(),
                "mediano".to_string(),
                "Error Rate Monitor".to_string(),
            );
            error_rate.set_description("API error rate and response time monitoring".to_string());
            error_rate.set_interval(60);
            error_rate.set_threshold(0.05);
            monitors.push(error_rate);
        }
        "high" | "critical" => {
            let mut usage = MonitorDef::new(
                "resource_usage".to_string(),
                "liviano".to_string(),
                "Resource Usage".to_string(),
            );
            usage.set_description("CPU and memory usage monitoring".to_string());
            usage.set_interval(60);
            monitors.push(usage);

            let mut error_rate = MonitorDef::new(
                "error_rate".to_string(),
                "mediano".to_string(),
                "Error Rate Monitor".to_string(),
            );
            error_rate.set_description("API error rate and response time monitoring".to_string());
            error_rate.set_interval(30);
            error_rate.set_threshold(0.02);
            monitors.push(error_rate);

            let mut intrusion = MonitorDef::new(
                "intrusion_detection".to_string(),
                "pesado".to_string(),
                "Intrusion Detection".to_string(),
            );
            intrusion.set_description("Security event and intrusion detection monitoring".to_string());
            intrusion.set_interval(30);
            intrusion.set_threshold(0.01);
            monitors.push(intrusion);

            let mut data_integrity = MonitorDef::new(
                "data_integrity".to_string(),
                "pesado".to_string(),
                "Data Integrity Monitor".to_string(),
            );
            data_integrity.set_description("Hash chain and data integrity verification".to_string());
            data_integrity.set_interval(300);
            data_integrity.set_threshold(0.0);
            monitors.push(data_integrity);
        }
        _ => {}
    }

    monitors
}

/// Build default actions based on niche type and data sensitivity.
pub(super) fn build_default_actions(niche_id: &str, data_sensitivity: &str) -> Vec<ActionDef> {
    let mut actions: Vec<ActionDef> = Vec::new();

    // Common actions for all niches
    let mut read = ActionDef::new(
        "read_data".to_string(),
        "db".to_string(),
        "Read Data".to_string(),
    );
    read.set_description("Read data from database".to_string());
    read.set_risk_level("low".to_string());
    actions.push(read);

    let mut create = ActionDef::new(
        "create_record".to_string(),
        "db".to_string(),
        "Create Record".to_string(),
    );
    create.set_description("Create a new database record".to_string());
    create.set_risk_level("medium".to_string());
    actions.push(create);

    // Financial/destructive actions require approval for sensitive data
    if data_sensitivity == "high" || data_sensitivity == "critical" {
        let mut delete = ActionDef::new(
            "delete_record".to_string(),
            "db".to_string(),
            "Delete Record".to_string(),
        );
        delete.set_description("Delete a database record (requires approval)".to_string());
        delete.set_requires_approval(true);
        delete.set_risk_level("critical".to_string());
        actions.push(delete);

        let mut bulk_update = ActionDef::new(
            "bulk_update".to_string(),
            "db".to_string(),
            "Bulk Update".to_string(),
        );
        bulk_update.set_description("Bulk update multiple records (requires approval)".to_string());
        bulk_update.set_requires_approval(true);
        bulk_update.set_risk_level("high".to_string());
        actions.push(bulk_update);
    }

    // Niche-specific actions
    if niche_id.contains("fintech") || niche_id.contains("banking") || niche_id.contains("defi") {
        let mut transfer = ActionDef::new(
            "financial_transfer".to_string(),
            "http".to_string(),
            "Financial Transfer".to_string(),
        );
        transfer.set_description("Execute a financial transfer (requires approval)".to_string());
        transfer.set_requires_approval(true);
        transfer.set_risk_level("critical".to_string());
        actions.push(transfer);
    }

    if niche_id.contains("health") || niche_id.contains("telemedicine") {
        let mut access_phi = ActionDef::new(
            "access_phi".to_string(),
            "db".to_string(),
            "Access PHI Data".to_string(),
        );
        access_phi.set_description("Access Protected Health Information (requires approval)".to_string());
        access_phi.set_requires_approval(true);
        access_phi.set_risk_level("critical".to_string());
        actions.push(access_phi);
    }

    actions
}

/// Build default database schema based on niche type.
pub(super) fn build_default_db_schema(niche_id: &str) -> Vec<DbTableDef> {
    let mut tables: Vec<DbTableDef> = Vec::new();

    // Common tables for all niches
    let mut users = DbTableDef::new("users".to_string(), "id".to_string());
    users.set_encrypted(true);
    users.add_column(ColumnDef::py_new("id".to_string(), "uuid".to_string()));
    users.add_column({
        let mut col = ColumnDef::py_new("email".to_string(), "text".to_string());
        col.set_unique(true);
        col.set_indexed(true);
        col
    });
    users.add_column({
        let mut col = ColumnDef::py_new("name".to_string(), "text".to_string());
        col.set_nullable(false);
        col
    });
    users.add_column({
        let mut col = ColumnDef::py_new("role".to_string(), "text".to_string());
        col.set_nullable(false);
        col.set_indexed(true);
        col
    });
    users.add_column(ColumnDef::py_new("created_at".to_string(), "datetime".to_string()));
    tables.push(users);

    let mut audit_log = DbTableDef::new("audit_log".to_string(), "id".to_string());
    audit_log.set_encrypted(false);
    audit_log.add_column(ColumnDef::py_new("id".to_string(), "uuid".to_string()));
    audit_log.add_column({
        let mut col = ColumnDef::py_new("user_id".to_string(), "uuid".to_string());
        col.set_indexed(true);
        col
    });
    audit_log.add_column({
        let mut col = ColumnDef::py_new("action".to_string(), "text".to_string());
        col.set_indexed(true);
        col.set_nullable(false);
        col
    });
    audit_log.add_column(ColumnDef::py_new("resource_type".to_string(), "text".to_string()));
    audit_log.add_column(ColumnDef::py_new("resource_id".to_string(), "text".to_string()));
    audit_log.add_column(ColumnDef::py_new("timestamp".to_string(), "datetime".to_string()));
    audit_log.add_column(ColumnDef::py_new("details".to_string(), "json".to_string()));
    tables.push(audit_log);

    // Niche-specific tables
    if niche_id.contains("crm") || niche_id.contains("sales") {
        let mut contacts = DbTableDef::new("contacts".to_string(), "id".to_string());
        contacts.add_column(ColumnDef::py_new("id".to_string(), "uuid".to_string()));
        contacts.add_column({
            let mut col = ColumnDef::py_new("name".to_string(), "text".to_string());
            col.set_nullable(false);
            col
        });
        contacts.add_column(ColumnDef::py_new("email".to_string(), "text".to_string()));
        contacts.add_column(ColumnDef::py_new("company".to_string(), "text".to_string()));
        contacts.add_column(ColumnDef::py_new("stage".to_string(), "text".to_string()));
        contacts.add_column(ColumnDef::py_new("value".to_string(), "currency".to_string()));
        tables.push(contacts);
    }

    if niche_id.contains("inventory") || niche_id.contains("warehouse") {
        let mut products = DbTableDef::new("products".to_string(), "id".to_string());
        products.add_column(ColumnDef::py_new("id".to_string(), "uuid".to_string()));
        products.add_column({
            let mut col = ColumnDef::py_new("name".to_string(), "text".to_string());
            col.set_nullable(false);
            col
        });
        products.add_column(ColumnDef::py_new("sku".to_string(), "text".to_string()));
        products.add_column(ColumnDef::py_new("quantity".to_string(), "integer".to_string()));
        products.add_column(ColumnDef::py_new("price".to_string(), "currency".to_string()));
        products.add_column(ColumnDef::py_new("min_stock".to_string(), "integer".to_string()));
        tables.push(products);
    }

    tables
}
