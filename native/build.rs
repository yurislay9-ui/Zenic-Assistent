/// PyO3 build script.
///
/// This file is required for PyO3 extension modules.
/// It instructs cargo to link against the Python interpreter
/// when building a cdylib for use as a Python extension.
fn main() {
    // PyO3 handles all the linking logic internally via its build.rs
    // when the "extension-module" feature is enabled.
    // This file exists as a placeholder and to emit any custom
    // build instructions if needed in the future.
}
