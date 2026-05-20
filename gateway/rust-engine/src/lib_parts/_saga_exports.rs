// ─── Saga Pattern WASM Exports ───────────────────────────────────────────
// Saga lifecycle, proration, and path validation WASM-bindgen functions.

use crate::types::*;
use crate::saga;
use wasm_bindgen::prelude::*;

/// Get all available Saga types
#[wasm_bindgen]
pub fn get_saga_types() -> String {
    let types: Vec<serde_json::Value> = saga::SagaType::all().iter().map(|st| {
        serde_json::json!({
            "id": st.as_str(),
            "display_name": st.display_name(),
            "description": st.description(),
        })
    }).collect();
    serde_json::to_string(&types).unwrap_or_else(|_| "[]".to_string())
}

/// Get a Saga definition by type
#[wasm_bindgen]
pub fn get_saga_definition(saga_type_name: &str) -> String {
    let saga_type = match saga::SagaType::from_str_value(saga_type_name) {
        Some(st) => st,
        None => return serde_json::json!({"error": format!("Unknown saga type: {}", saga_type_name)}).to_string(),
    };
    let definition = saga::get_saga_definition(saga_type);
    serde_json::to_string(&definition).unwrap_or_else(|_| "{}".to_string())
}

/// Initialize a new Saga execution
#[wasm_bindgen]
pub fn create_saga_execution(saga_type_name: &str, tenant_id: &str, subscription_id_json: &str, metadata_json: &str) -> String {
    let saga_type = match saga::SagaType::from_str_value(saga_type_name) {
        Some(st) => st,
        None => return serde_json::json!({"error": format!("Unknown saga type: {}", saga_type_name)}).to_string(),
    };

    let subscription_id: Option<String> = serde_json::from_str(subscription_id_json).unwrap_or(None);
    let metadata: Option<String> = serde_json::from_str(metadata_json).unwrap_or(None);

    let execution = saga::create_saga_execution(saga_type, tenant_id.to_string(), subscription_id, metadata);
    serde_json::to_string(&execution).unwrap_or_else(|_| "{}".to_string())
}

/// Advance a Saga step (mark as success or failure)
#[wasm_bindgen]
pub fn advance_saga_step(execution_json: &str, step_index: u32, success: bool, output_data_json: &str, error_message_json: &str) -> String {
    let mut execution: saga::SagaExecution = match serde_json::from_str(execution_json) {
        Ok(e) => e,
        Err(err) => return serde_json::json!({"error": format!("Invalid execution JSON: {}", err)}).to_string(),
    };

    let output_data: Option<String> = serde_json::from_str(output_data_json).unwrap_or(None);
    let error_message: Option<String> = serde_json::from_str(error_message_json).unwrap_or(None);

    let new_status = saga::advance_saga_step(&mut execution, step_index, success, output_data, error_message);
    serde_json::json!({
        "execution_id": execution.execution_id,
        "saga_type": execution.saga_type.as_str(),
        "status": new_status.as_str(),
        "current_step_index": execution.current_step_index,
        "execution": execution,
    }).to_string()
}

/// Complete a compensation step in a Saga
#[wasm_bindgen]
pub fn complete_compensation_step(execution_json: &str, step_index: u32, success: bool, compensation_error_json: &str) -> String {
    let mut execution: saga::SagaExecution = match serde_json::from_str(execution_json) {
        Ok(e) => e,
        Err(err) => return serde_json::json!({"error": format!("Invalid execution JSON: {}", err)}).to_string(),
    };

    let compensation_error: Option<String> = serde_json::from_str(compensation_error_json).unwrap_or(None);

    let new_status = saga::complete_compensation_step(&mut execution, step_index, success, compensation_error);
    serde_json::json!({
        "execution_id": execution.execution_id,
        "saga_type": execution.saga_type.as_str(),
        "status": new_status.as_str(),
        "current_step_index": execution.current_step_index,
        "execution": execution,
    }).to_string()
}

/// Calculate proration for tier upgrade/downgrade
#[wasm_bindgen]
pub fn calculate_proration(current_tier_name: &str, new_tier_name: &str, days_remaining: u32, days_in_period: u32) -> String {
    let current_tier = match SubscriptionTier::from_str_value(current_tier_name) {
        Some(t) => t,
        None => return serde_json::json!({"error": format!("Unknown current tier: {}", current_tier_name)}).to_string(),
    };

    let new_tier = match SubscriptionTier::from_str_value(new_tier_name) {
        Some(t) => t,
        None => return serde_json::json!({"error": format!("Unknown new tier: {}", new_tier_name)}).to_string(),
    };

    let result = saga::calculate_proration(current_tier, new_tier, days_remaining, days_in_period);
    serde_json::to_string(&result).unwrap_or_else(|_| "{}".to_string())
}

/// Validate an upgrade path
#[wasm_bindgen]
pub fn validate_upgrade_path(current_tier_name: &str, new_tier_name: &str) -> String {
    let current_tier = match SubscriptionTier::from_str_value(current_tier_name) {
        Some(t) => t,
        None => return serde_json::json!({"error": format!("Unknown current tier: {}", current_tier_name), "valid": false}).to_string(),
    };

    let new_tier = match SubscriptionTier::from_str_value(new_tier_name) {
        Some(t) => t,
        None => return serde_json::json!({"error": format!("Unknown new tier: {}", new_tier_name), "valid": false}).to_string(),
    };

    match saga::validate_upgrade_path(current_tier, new_tier) {
        Ok(()) => serde_json::json!({
            "valid": true,
            "current_tier": current_tier_name,
            "new_tier": new_tier_name,
            "message": format!("Upgrade from {} to {} is valid", current_tier.display_name(), new_tier.display_name()),
        }).to_string(),
        Err(err) => serde_json::json!({
            "valid": false,
            "current_tier": current_tier_name,
            "new_tier": new_tier_name,
            "error": err,
        }).to_string(),
    }
}

/// Validate a downgrade path
#[wasm_bindgen]
pub fn validate_downgrade_path(current_tier_name: &str, new_tier_name: &str) -> String {
    let current_tier = match SubscriptionTier::from_str_value(current_tier_name) {
        Some(t) => t,
        None => return serde_json::json!({"error": format!("Unknown current tier: {}", current_tier_name), "valid": false}).to_string(),
    };

    let new_tier = match SubscriptionTier::from_str_value(new_tier_name) {
        Some(t) => t,
        None => return serde_json::json!({"error": format!("Unknown new tier: {}", new_tier_name), "valid": false}).to_string(),
    };

    match saga::validate_downgrade_path(current_tier, new_tier) {
        Ok(()) => serde_json::json!({
            "valid": true,
            "current_tier": current_tier_name,
            "new_tier": new_tier_name,
            "message": format!("Downgrade from {} to {} is valid", current_tier.display_name(), new_tier.display_name()),
        }).to_string(),
        Err(err) => serde_json::json!({
            "valid": false,
            "current_tier": current_tier_name,
            "new_tier": new_tier_name,
            "error": err,
        }).to_string(),
    }
}
