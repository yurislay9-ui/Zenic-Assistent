// ─── Saga Pricing / Proration Logic ──────────────────────────────────────
// ProrationResult, calculate_proration, validate_upgrade_path,
// validate_downgrade_path, tier_rank, sha256_short, chrono_now_iso

use crate::types::*;
use serde::{Deserialize, Serialize};

/// Result of a proration calculation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProrationResult {
    pub current_tier: String,
    pub new_tier: String,
    pub current_monthly_usdt: f64,
    pub new_monthly_usdt: f64,
    pub days_remaining: u32,
    pub days_in_period: u32,
    pub remaining_fraction: f64,
    pub credit_usdt: f64,
    pub charge_usdt: f64,
    pub net_amount_usdt: f64,
    pub is_upgrade: bool,
    pub payment_currency: String,
    pub payment_network: String,
}

/// Calculate proration amount for an upgrade/downgrade
pub fn calculate_proration(
    current_tier: SubscriptionTier,
    new_tier: SubscriptionTier,
    days_remaining: u32,
    days_in_period: u32,
) -> ProrationResult {
    let current_monthly = current_tier.monthly_price_usdt();
    let new_monthly = new_tier.monthly_price_usdt();
    let daily_current = current_monthly / 30.0;
    let daily_new = new_monthly / 30.0;

    let remaining_fraction = if days_in_period > 0 { days_remaining as f64 / days_in_period as f64 } else { 0.0 };

    let credit = daily_current * days_remaining as f64;
    let charge = daily_new * days_remaining as f64;
    let net_amount = charge - credit;

    ProrationResult {
        current_tier: current_tier.as_str().to_string(),
        new_tier: new_tier.as_str().to_string(),
        current_monthly_usdt: current_monthly,
        new_monthly_usdt: new_monthly,
        days_remaining,
        days_in_period,
        remaining_fraction,
        credit_usdt: credit,
        charge_usdt: charge,
        net_amount_usdt: net_amount,
        is_upgrade: net_amount > 0.0,
        payment_currency: "USDT".to_string(),
        payment_network: "TRC20".to_string(),
    }
}

/// Validate an upgrade path (must go from lower to higher tier)
pub fn validate_upgrade_path(current: SubscriptionTier, new: SubscriptionTier) -> Result<(), String> {
    let current_rank = tier_rank(current);
    let new_rank = tier_rank(new);

    if new_rank <= current_rank {
        return Err(format!("Invalid upgrade: {} → {}. New tier must be higher than current.", current.display_name(), new.display_name()));
    }
    Ok(())
}

/// Validate a downgrade path (must go from higher to lower tier)
pub fn validate_downgrade_path(current: SubscriptionTier, new: SubscriptionTier) -> Result<(), String> {
    let current_rank = tier_rank(current);
    let new_rank = tier_rank(new);

    if new_rank >= current_rank {
        return Err(format!("Invalid downgrade: {} → {}. New tier must be lower than current.", current.display_name(), new.display_name()));
    }
    Ok(())
}

/// Tier ranking for upgrade/downgrade validation
pub(crate) fn tier_rank(tier: SubscriptionTier) -> u32 {
    match tier {
        SubscriptionTier::Starter => 1,
        SubscriptionTier::Business => 2,
        SubscriptionTier::Enterprise => 3,
        SubscriptionTier::OnPremiseEnterprise => 4,
        SubscriptionTier::Trial => 0, // Trial is below all paid tiers
    }
}

// ─── Internal Helpers (duplicated from lib.rs to avoid circular imports) ──

pub(crate) fn sha256_short(input: &str) -> String {
    use sha2::{Sha256, Digest};
    let mut hasher = Sha256::new();
    hasher.update(input.as_bytes());
    format!("{:x}", hasher.finalize())[..12].to_string()
}

pub(crate) fn chrono_now_iso() -> String {
    chrono::Utc::now().to_rfc3339()
}
