// ─── Subscription & Payment WASM Exports ──────────────────────────────────

use wasm_bindgen::prelude::*;
use types::*;
use crate::helpers::{sha256_short, chrono_now_iso, chrono_future_iso};

#[wasm_bindgen]
pub fn get_trial_config() -> String {
    serde_json::to_string(&TrialConfig::default()).unwrap_or_else(|_| "{}".to_string())
}

#[wasm_bindgen]
pub fn validate_trc20_address(address: &str) -> String {
    let valid = address.starts_with('T') && address.len() == 34 && address[1..].chars().all(|c| c.is_alphanumeric());
    serde_json::json!({
        "address": address,
        "valid": valid,
        "network": "TRC20",
        "currency": "USDT",
        "reason": if valid { "Valid TRC20 address format" } else { "TRC20 address must start with 'T' and be 34 characters alphanumeric" },
    }).to_string()
}

#[wasm_bindgen]
pub fn create_trial_subscription(tenant_id: &str, email: &str) -> String {
    let config = TrialConfig::default();
    let subscription = Subscription {
        id: format!("sub_trial_{}", sha256_short(&format!("{}:{}", tenant_id, email))),
        tenant_id: tenant_id.to_string(),
        tier: SubscriptionTier::Trial,
        status: SubscriptionStatus::Trial,
        payment_method: PaymentMethod::UsdtTrc20,
        billing_wallet: String::new(),
        add_ons: vec![],
        started_at: chrono_now_iso(),
        current_period_end: chrono_future_iso(config.duration_days as i64),
        trial_ends_at: Some(chrono_future_iso(config.duration_days as i64)),
        auto_renew: false,
        last_payment_tx_hash: None,
        cancelled_at: None,
        cancellation_reason: None,
    };

    serde_json::json!({
        "subscription": subscription,
        "trial_config": config,
        "mandatory_for_all": true,
        "trial_is_prerequisite": true,
        "message": format!("Trial de {} días activado. Acceso completo al Plan Business.", config.duration_days),
        "payment_required": false,
        "payment_currency": "USDT",
        "payment_network": "TRC20",
    }).to_string()
}

#[wasm_bindgen]
pub fn convert_trial_to_paid(tenant_id: &str, tier_name: &str, wallet_address: &str) -> String {
    let tier = match SubscriptionTier::from_str_value(tier_name) {
        Some(t) if t != SubscriptionTier::Trial => t,
        _ => return serde_json::json!({"error": "Must convert to a paid tier"}).to_string(),
    };

    let wallet_valid = wallet_address.starts_with('T') && wallet_address.len() == 34;
    if !wallet_valid {
        return serde_json::json!({"error": "Invalid TRC20 wallet address"}).to_string();
    }

    let monthly = tier.monthly_price_usdt();
    let setup = tier.setup_fee_usdt();
    let first_payment = monthly + setup;

    let subscription = Subscription {
        id: format!("sub_{}", sha256_short(&format!("{}:{}", tenant_id, tier_name))),
        tenant_id: tenant_id.to_string(),
        tier,
        status: SubscriptionStatus::Active,
        payment_method: PaymentMethod::UsdtTrc20,
        billing_wallet: wallet_address.to_string(),
        add_ons: vec![],
        started_at: chrono_now_iso(),
        current_period_end: chrono_future_iso(30),
        trial_ends_at: None,
        auto_renew: true,
        last_payment_tx_hash: None,
        cancelled_at: None,
        cancellation_reason: None,
    };

    serde_json::json!({
        "subscription": subscription,
        "payment_required": first_payment,
        "payment_currency": "USDT",
        "payment_network": "TRC20",
        "breakdown": { "monthly_usdt": monthly, "setup_fee_usdt": setup, "first_payment_usdt": first_payment },
        "message": format!("Suscripción {} activada. Pago de {} USDT (TRC20) requerido.", tier.display_name(), first_payment),
    }).to_string()
}

// ─── Manual Payment Verification Functions ────────────────────────────────

#[wasm_bindgen]
pub fn get_payment_verification_methods() -> String {
    let methods = vec![
        serde_json::json!({
            "id": "manual_admin",
            "display_name": "Verificación Manual por Admin",
            "description": "Un administrador verifica manualmente el pago USDT TRC20",
            "currency": "USDT",
            "network": "TRC20",
        }),
        serde_json::json!({
            "id": "semi_manual_onchain",
            "display_name": "Verificación Semi-Manual On-Chain",
            "description": "El sistema verifica on-chain, un admin aprueba",
            "currency": "USDT",
            "network": "TRC20",
        }),
    ];
    serde_json::to_string(&methods).unwrap_or_else(|_| "[]".to_string())
}

#[wasm_bindgen]
pub fn is_trial_mandatory() -> String {
    let config = TrialConfig::default();
    serde_json::json!({
        "mandatory_for_all": config.mandatory_for_all,
        "trial_is_prerequisite": config.trial_is_prerequisite,
        "duration_days": config.duration_days,
        "granted_tier": config.granted_tier.as_str(),
        "message": "Todos los usuarios deben iniciar con el trial de 14 días del Plan Business. No se puede saltar al pago directamente.",
        "payment_currency": "USDT",
        "payment_network": "TRC20",
    }).to_string()
}

#[wasm_bindgen]
pub fn create_manual_payment_request(subscription_id: &str, amount_usdt: f64, wallet_from: &str, platform_wallet: &str) -> String {
    let verification = ManualPaymentVerification {
        payment_id: format!("pay_{}", sha256_short(&format!("{}:{}:{}", subscription_id, amount_usdt, wallet_from))),
        subscription_id: subscription_id.to_string(),
        amount_usdt,
        wallet_from: wallet_from.to_string(),
        wallet_to: platform_wallet.to_string(),
        tx_hash: None,
        verification_method: PaymentVerificationMethod::ManualAdmin,
        status: ManualPaymentStatus::AwaitingPayment,
        admin_notes: None,
        confirmed_by: None,
        confirmed_at: None,
        created_at: chrono_now_iso(),
    };

    serde_json::json!({
        "payment_request": verification,
        "instructions": {
            "step1": "Envía exactamente {amount_usdt} USDT por la red TRC20 a la wallet del platform",
            "step2": "Copia el hash de la transacción TRC20",
            "step3": "Proporciona el tx_hash para verificación manual por admin",
            "step4": "Un administrador confirmará tu pago manualmente",
        },
        "platform_wallet": platform_wallet,
        "amount_usdt": amount_usdt,
        "payment_currency": "USDT",
        "payment_network": "TRC20",
        "estimated_confirmation_time": "1-24 horas (verificación manual por admin)",
    }).to_string()
}

#[wasm_bindgen]
pub fn confirm_manual_payment(payment_id: &str, tx_hash: &str, confirmed_by: &str) -> String {
    // Validate tx hash format
    let tx_valid = tx_hash.len() == 64 && tx_hash.chars().all(|c| c.is_ascii_hexdigit());

    if !tx_valid {
        return serde_json::json!({
            "error": "Invalid TRC20 transaction hash",
            "details": "TRC20 tx hash must be 64 hex characters",
        }).to_string();
    }

    serde_json::json!({
        "payment_id": payment_id,
        "tx_hash": tx_hash,
        "status": "awaiting_confirmation",
        "confirmed_by": confirmed_by,
        "message": "Pago registrado. Un administrador debe confirmar manualmente la recepción del USDT TRC20.",
        "payment_currency": "USDT",
        "payment_network": "TRC20",
    }).to_string()
}
