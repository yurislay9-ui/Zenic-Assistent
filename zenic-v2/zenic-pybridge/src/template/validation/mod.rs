//! Template validation, missing fields, field setting, and serialization functions.

mod core;
mod serialization;

pub use core::{template_validate, template_missing_fields, template_set_field};
pub use serialization::template_to_yaml;
