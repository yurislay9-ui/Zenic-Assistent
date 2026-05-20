// ─── Niche API Functions ────────────────────────────────────────────────
// log_niche_error(), get_niche_categories(), get_niche_category_display_names()

use pyo3::prelude::*;

use super::enums::NicheCategory;

/// Log a niche-related error without panicking.
pub(crate) fn log_niche_error(msg: &str) {
    eprintln!("[ZENIC-NICHE-ERROR] {}", msg);
}

/// Get all available niche categories as a list of strings.
#[pyfunction]
pub fn get_niche_categories(py: Python<'_>) -> PyResult<Vec<String>> {
    Ok(NicheCategory::all().iter().map(|c| c.as_str().to_string()).collect())
}

/// Get display names for all niche categories.
#[pyfunction]
pub fn get_niche_category_display_names(py: Python<'_>) -> PyResult<Vec<String>> {
    Ok(NicheCategory::all().iter().map(|c| c.display_name().to_string()).collect())
}
