//! Apply extraction matches to a template dict.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use super::types::*;

/// Apply extraction matches to a template dict.
///
/// Sets field values in the template for each match that meets
/// the minimum confidence threshold. Also recalculates completeness.
///
/// Parameters
/// ----------
/// template_dict : dict
///     The template dict (will be modified in-place).
/// matches : list[FieldMatch]
///     The field matches to apply.
///
/// Returns
/// -------
/// bool
///     True if at least one field was successfully set.
#[pyfunction]
pub fn extractor_apply_matches(
    template_dict: &Bound<'_, PyDict>,
    matches: &Bound<'_, PyList>,
) -> PyResult<bool> {
    let match_list: Vec<FieldMatch> = matches.extract()?;
    if match_list.is_empty() {
        return Ok(false);
    }

    let mut any_applied = false;

    // Use template_set_field from the template module for each match
    for field_match in &match_list {
        if field_match.confidence() < MIN_CONFIDENCE_THRESHOLD {
            continue;
        }

        let section_id = field_match.section_id();
        let field_name = field_match.field_name();
        let value = field_match.value();

        // Try to set the field using the existing template API
        let result = crate::template::template_set_field(
            template_dict,
            section_id,
            field_name,
            value.into(),
        );

        match result {
            Ok(true) => any_applied = true,
            Ok(false) => {
                // Field not found in the specified section; try to find it
                // This can happen when section_id is empty
                if section_id.is_empty() {
                    if let Ok(found) = try_set_field_any_section(template_dict, field_name, value) {
                        if found {
                            any_applied = true;
                        }
                    }
                }
            }
            Err(_) => continue,
        }
    }

    Ok(any_applied)
}

/// Try to set a field value by searching all sections.
fn try_set_field_any_section(
    template_dict: &Bound<'_, PyDict>,
    field_name: &str,
    value: &str,
) -> PyResult<bool> {
    let template_obj = match template_dict.get_item("template") {
        Ok(Some(t)) => t,
        _ => return Ok(false),
    };

    let template_pydict: &Bound<'_, PyDict> = match template_obj.downcast() {
        Ok(d) => d,
        _ => return Ok(false),
    };

    let sections_obj = match template_pydict.get_item("sections") {
        Ok(Some(s)) => s,
        _ => return Ok(false),
    };

    let sections: &Bound<'_, PyDict> = match sections_obj.downcast() {
        Ok(d) => d,
        _ => return Ok(false),
    };

    for (section_key, section_val) in sections.iter() {
        let section_dict: &Bound<'_, PyDict> = match section_val.downcast() {
            Ok(d) => d,
            _ => continue,
        };

        if let Ok(Some(_)) = section_dict.get_item(field_name) {
            let section_id: String = section_key.extract().unwrap_or_default();
            return crate::template::template_set_field(
                template_dict,
                &section_id,
                field_name,
                value.into(),
            );
        }
    }

    Ok(false)
}
