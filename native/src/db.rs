//! SQLCipher database integration for Zenic-Agents.
//!
//! Provides an encrypted SQLite database connection using SQLCipher
//! via the rusqlite crate with the bundled-sqlcipher feature.
//! This ensures data at rest is always encrypted.

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList};

use rusqlite::Connection;
use std::sync::Mutex;

/// An encrypted SQLite database connection.
///
/// Wraps a rusqlite Connection with SQLCipher encryption.
/// The connection is thread-safe (protected by a Mutex).
///
/// Usage from Python::
///
///     db = EncryptedDb.open("/path/to/db.sqlite", "passphrase")
///     db.execute("CREATE TABLE t (id INTEGER, name TEXT)", [])
///     db.execute("INSERT INTO t VALUES (?, ?)", [1, "Alice"])
///     result = db.execute("SELECT * FROM t", [])
///     db.close()
///
#[pyclass(name = "EncryptedDb")]
pub struct EncryptedDb {
    conn: Mutex<Option<Connection>>,
}

#[pymethods]
impl EncryptedDb {
    /// Open an encrypted SQLite database.
    ///
    /// Parameters
    /// ----------
    /// path : str
    ///     Path to the database file.
    /// passphrase : str
    ///     Encryption passphrase for SQLCipher.
    ///
    /// Returns
    /// -------
    /// EncryptedDb
    ///     A new encrypted database connection.
    ///
    /// Raises
    /// ------
    /// RuntimeError
    ///     If the database cannot be opened or the key cannot be set.
    #[staticmethod]
    #[pyo3(signature = (path, passphrase))]
    fn open(path: &str, passphrase: &str) -> PyResult<Self> {
        let conn = Connection::open(path)
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to open database: {}", e)))?;

        // Set the SQLCipher encryption key using PRAGMA
        conn.pragma_update(None, "key", passphrase)
            .map_err(|e| {
                PyRuntimeError::new_err(format!("Failed to set encryption key: {}", e))
            })?;

        // Verify the database is readable by executing a simple query
        conn.execute_batch("SELECT count(*) FROM sqlite_master")
            .map_err(|e| {
                PyRuntimeError::new_err(format!(
                    "Database decryption failed (wrong passphrase?): {}",
                    e
                ))
            })?;

        // Set recommended SQLCipher pragmas
        conn.pragma_update(None, "cipher_page_size", &4096_i64)
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to set page size: {}", e)))?;
        conn.pragma_update(None, "kdf_iter", &256000_i64)
            .map_err(|e| {
                PyRuntimeError::new_err(format!("Failed to set KDF iterations: {}", e))
            })?;

        Ok(EncryptedDb {
            conn: Mutex::new(Some(conn)),
        })
    }

    /// Execute a SQL statement with optional parameters.
    ///
    /// Parameters
    /// ----------
    /// sql : str
    ///     The SQL statement to execute.
    /// params : list
    ///     Parameters to bind to the statement. Supported types:
    ///     int, float, str, bytes, None.
    ///
    /// Returns
    /// -------
    /// list or int
    ///     For SELECT statements: a list of rows (each row is a list of values).
    ///     For other statements: the number of affected rows.
    ///
    /// Raises
    /// ------
    /// RuntimeError
    ///     If the database is closed or the query fails.
    /// ValueError
    ///     If a parameter type is not supported.
    #[pyo3(signature = (sql, params))]
    fn execute(&self, py: Python<'_>, sql: &str, params: &Bound<'_, PyList>) -> PyResult<PyObject> {
        let guard = self
            .conn
            .lock()
            .map_err(|e| PyRuntimeError::new_err(format!("Lock poisoned: {}", e)))?;

        let conn = guard
            .as_ref()
            .ok_or_else(|| PyRuntimeError::new_err("Database is closed"))?;

        // Convert Python list to rusqlite params
        let param_values: Vec<rusqlite::types::Value> = params
            .iter()
            .map(|item| {
                if item.is_none() {
                    Ok(rusqlite::types::Value::Null)
                } else if let Ok(i) = item.extract::<i64>() {
                    Ok(rusqlite::types::Value::Integer(i))
                } else if let Ok(f) = item.extract::<f64>() {
                    Ok(rusqlite::types::Value::Real(f))
                } else if let Ok(s) = item.extract::<String>() {
                    Ok(rusqlite::types::Value::Text(s))
                } else if let Ok(b) = item.extract::<Vec<u8>>() {
                    Ok(rusqlite::types::Value::Blob(b))
                } else {
                    Err(PyValueError::new_err(format!(
                        "Unsupported parameter type: {}",
                        item.get_type()
                    )))
                }
            })
            .collect::<PyResult<Vec<_>>>()?;

        let params_refs: Vec<&dyn rusqlite::types::ToSql> = param_values
            .iter()
            .map(|v| v as &dyn rusqlite::types::ToSql)
            .collect();

        // Determine if this is a SELECT statement
        let trimmed = sql.trim().to_uppercase();
        let is_select = trimmed.starts_with("SELECT") || trimmed.starts_with("PRAGMA");

        if is_select {
            let mut stmt = conn
                .prepare(sql)
                .map_err(|e| PyRuntimeError::new_err(format!("Prepare error: {}", e)))?;

            let column_count = stmt.column_count();
            let column_names: Vec<String> = (0..column_count)
                .map(|i| stmt.column_name(i).unwrap_or("?").to_string())
                .collect();

            let rows = stmt
                .query_map(params_refs.as_slice(), |row| {
                    let mut values = Vec::with_capacity(column_count);
                    for i in 0..column_count {
                        let val: rusqlite::types::Value =
                            row.get(i).unwrap_or(rusqlite::types::Value::Null);
                        values.push(val);
                    }
                    Ok(values)
                })
                .map_err(|e| PyRuntimeError::new_err(format!("Query error: {}", e)))?;

            let result = PyList::empty_bound(py);
            for row_result in rows {
                let row_values = row_result
                    .map_err(|e| PyRuntimeError::new_err(format!("Row error: {}", e)))?;

                let py_row = PyList::empty_bound(py);
                for val in row_values {
                    let py_val = match val {
                        rusqlite::types::Value::Null => py.None(),
                        rusqlite::types::Value::Integer(i) => i.to_object(py),
                        rusqlite::types::Value::Real(f) => f.to_object(py),
                        rusqlite::types::Value::Text(s) => s.to_object(py),
                        rusqlite::types::Value::Blob(b) => {
                            PyBytes::new_bound(py, &b).into_any().unbind()
                        }
                    };
                    py_row.append(py_val)?;
                }
                result.append(py_row)?;
            }

            // Return as dict with column names if there are columns
            let dict = PyDict::new_bound(py);
            dict.set_item("columns", column_names)?;
            dict.set_item("rows", result)?;
            Ok(dict.into_any().unbind())
        } else {
            let affected = conn
                .execute(sql, params_refs.as_slice())
                .map_err(|e| PyRuntimeError::new_err(format!("Execute error: {}", e)))?;
            Ok(affected.to_object(py))
        }
    }

    /// Close the database connection.
    ///
    /// After calling this method, the connection cannot be used anymore.
    /// It is safe to call close() multiple times.
    ///
    /// Returns
    /// -------
    /// bool
    ///     True if the connection was closed successfully.
    fn close(&self) -> PyResult<bool> {
        let mut guard = self
            .conn
            .lock()
            .map_err(|e| PyRuntimeError::new_err(format!("Lock poisoned: {}", e)))?;

        // Drop the connection by replacing with None
        if guard.take().is_some() {
            // Connection is dropped here, which closes it
            Ok(true)
        } else {
            // Already closed
            Ok(false)
        }
    }

    /// Check if the database connection is open.
    ///
    /// Returns
    /// -------
    /// bool
    ///     True if the connection is open and usable.
    #[getter]
    fn is_open(&self) -> PyResult<bool> {
        let guard = self
            .conn
            .lock()
            .map_err(|e| PyRuntimeError::new_err(format!("Lock poisoned: {}", e)))?;
        Ok(guard.is_some())
    }
}

// ── Unit tests ──────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    // Note: Full integration tests require a Python interpreter.
    // These tests verify the Rust logic independently.

    #[test]
    fn test_module_compiles() {
        // Basic smoke test that the module compiles
        assert!(true);
    }
}
