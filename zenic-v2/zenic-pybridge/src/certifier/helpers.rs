use pyo3::prelude::*;
use pyo3::types::PyDict;
use std::collections::HashMap;

use super::config::*;
use super::schema_types::*;

// ═══════════════════════════════════════════════════════════════
//  Internal Helpers
// ═══════════════════════════════════════════════════════════════

/// Generate a blueprint ID from niche_id and timestamp.
pub(super) fn generate_blueprint_id(niche_id: &str) -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let ts = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0);
    format!("bp-{}-{:016x}", niche_id, ts)
}

/// Compute a SHA-256 hash of the canonical form of a BlueprintConfig.
///
/// The canonical form is a deterministic JSON serialization with
/// sorted keys, ensuring idempotent hashing.
pub(super) fn compute_canonical_hash(config: &BlueprintConfig) -> String {
    // Build a canonical representation for hashing
    let mut canonical_parts: Vec<String> = Vec::new();

    // Core identity
    canonical_parts.push(format!("niche_id:{}", config.niche_id));
    canonical_parts.push(format!("business_name:{}", config.business_name));
    canonical_parts.push(format!("business_type:{}", config.business_type));
    canonical_parts.push(format!("domain:{}", config.domain));
    if !config.subdomain.is_empty() {
        canonical_parts.push(format!("subdomain:{}", config.subdomain));
    }
    canonical_parts.push(format!("data_sensitivity:{}", config.data_sensitivity));
    canonical_parts.push(format!("version:{}", config.version));

    // Compliance (sorted)
    let mut compliance_sorted = config.compliance.clone();
    compliance_sorted.sort();
    canonical_parts.push(format!("compliance:{}", compliance_sorted.join(",")));

    // Tags (sorted)
    let mut tags_sorted = config.tags.clone();
    tags_sorted.sort();
    canonical_parts.push(format!("tags:{}", tags_sorted.join(",")));

    // Settings (sorted)
    let mut settings_sorted: Vec<(String, String)> =
        config.settings.iter().map(|(k, v)| (k.clone(), v.clone())).collect();
    settings_sorted.sort_by(|a, b| a.0.cmp(&b.0));
    let settings_str: Vec<String> =
        settings_sorted.iter().map(|(k, v)| format!("{}={}", k, v)).collect();
    canonical_parts.push(format!("settings:{}", settings_str.join(",")));

    // DB tables
    let mut db_parts: Vec<String> = Vec::new();
    for table in &config.db_schema {
        let mut col_parts: Vec<String> = Vec::new();
        for col in &table.columns {
            col_parts.push(format!("{}:{}", col.name, col.col_type));
        }
        col_parts.sort();
        db_parts.push(format!("{}[pk={},enc={},cols={}]",
            table.table_name,
            table.primary_key,
            table.encrypted,
            col_parts.join(";"),
        ));
    }
    db_parts.sort();
    canonical_parts.push(format!("db:{}", db_parts.join("|")));

    // Monitors
    let mut mon_parts: Vec<String> = Vec::new();
    for m in &config.monitors {
        mon_parts.push(format!("{}:{}:{}", m.monitor_id, m.monitor_type, m.interval_seconds));
    }
    mon_parts.sort();
    canonical_parts.push(format!("monitors:{}", mon_parts.join("|")));

    // Actions
    let mut act_parts: Vec<String> = Vec::new();
    for a in &config.actions {
        act_parts.push(format!("{}:{}:{}", a.action_id, a.action_type, a.risk_level));
    }
    act_parts.sort();
    canonical_parts.push(format!("actions:{}", act_parts.join("|")));

    let canonical_string = canonical_parts.join("\n");

    // Compute SHA-256 using the existing hash module
    crate::hash::blake3_hash(canonical_string.as_bytes())
}

/// Extract a field value from a template dict section.
pub(super) fn get_template_field_value(
    template_dict: &Bound<'_, PyDict>,
    section_id: &str,
    field_name: &str,
) -> Option<String> {
    let template_obj = template_dict.get_item("template").ok().flatten()?;
    let template_pydict: &Bound<'_, PyDict> = template_obj.downcast().ok()?;
    let sections_obj = template_pydict.get_item("sections").ok().flatten()?;
    let sections: &Bound<'_, PyDict> = sections_obj.downcast().ok()?;
    let section_val = sections.get_item(section_id).ok().flatten()?;
    let section_dict: &Bound<'_, PyDict> = section_val.downcast().ok()?;
    let field_val = section_dict.get_item(field_name).ok().flatten()?;
    let field_dict: &Bound<'_, PyDict> = field_val.downcast().ok()?;
    let value_obj = field_dict.get_item("value").ok().flatten()?;

    if value_obj.is_none() {
        return None;
    }

    value_obj.extract::<String>().ok()
}

/// Get the compliance list from template metadata.
pub(super) fn get_template_compliance(template_dict: &Bound<'_, PyDict>) -> Vec<String> {
    let template_obj = match template_dict.get_item("template") {
        Ok(Some(t)) => t,
        _ => return Vec::new(),
    };
    let template_pydict: &Bound<'_, PyDict> = match template_obj.downcast() {
        Ok(d) => d,
        _ => return Vec::new(),
    };
    let metadata_obj = match template_pydict.get_item("metadata") {
        Ok(Some(m)) => m,
        _ => return Vec::new(),
    };
    let metadata: &Bound<'_, PyDict> = match metadata_obj.downcast() {
        Ok(d) => d,
        _ => return Vec::new(),
    };

    match metadata.get_item("compliance") {
        Ok(Some(v)) => v.extract::<Vec<String>>().unwrap_or_default(),
        _ => Vec::new(),
    }
}

/// Get metadata string field from template.
pub(super) fn get_template_metadata_str(
    template_dict: &Bound<'_, PyDict>,
    key: &str,
) -> String {
    let template_obj = match template_dict.get_item("template") {
        Ok(Some(t)) => t,
        _ => return String::new(),
    };
    let template_pydict: &Bound<'_, PyDict> = match template_obj.downcast() {
        Ok(d) => d,
        _ => return String::new(),
    };
    let metadata_obj = match template_pydict.get_item("metadata") {
        Ok(Some(m)) => m,
        _ => return String::new(),
    };
    let metadata: &Bound<'_, PyDict> = match metadata_obj.downcast() {
        Ok(d) => d,
        _ => return String::new(),
    };

    metadata
        .get_item(key)
        .ok()
        .flatten()
        .and_then(|v| v.extract().ok())
        .unwrap_or_default()
}

/// Extract all settings from a template dict.
pub(super) fn extract_settings_from_template(
    template_dict: &Bound<'_, PyDict>,
) -> HashMap<String, String> {
    let mut settings: HashMap<String, String> = HashMap::new();

    let template_obj = match template_dict.get_item("template") {
        Ok(Some(t)) => t,
        _ => return settings,
    };
    let template_pydict: &Bound<'_, PyDict> = match template_obj.downcast() {
        Ok(d) => d,
        _ => return settings,
    };
    let sections_obj = match template_pydict.get_item("sections") {
        Ok(Some(s)) => s,
        _ => return settings,
    };
    let sections: &Bound<'_, PyDict> = match sections_obj.downcast() {
        Ok(d) => d,
        _ => return settings,
    };

    for (_, section_val) in sections.iter() {
        let section_dict: &Bound<'_, PyDict> = match section_val.downcast() {
            Ok(d) => d,
            _ => continue,
        };

        for (field_key, field_val) in section_dict.iter() {
            let field_name: String = match field_key.extract() {
                Ok(s) => s,
                _ => continue,
            };
            if field_name.starts_with('_') {
                continue;
            }

            let field_dict: &Bound<'_, PyDict> = match field_val.downcast() {
                Ok(d) => d,
                _ => continue,
            };

            let value_obj = match field_dict.get_item("value") {
                Ok(Some(v)) => v,
                _ => continue,
            };

            if value_obj.is_none() {
                continue;
            }

            if let Ok(str_val) = value_obj.extract::<String>() {
                if !str_val.is_empty() {
                    settings.insert(field_name, str_val);
                }
            }
        }
    }

    settings
}
