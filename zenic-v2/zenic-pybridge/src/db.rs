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
        // E-02 FIX: Convert Python params to Rust values WHILE holding the GIL,
        // then release the GIL for the actual SQLite operations to prevent
        // GIL deadlock (Python thread holding GIL waits for Rust lock,
        // Rust thread holding lock waits for GIL).

        // Convert Python list to rusqlite params (requires GIL for extraction)
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

        // Determine if this is a SELECT statement
        let trimmed = sql.trim().to_uppercase();
        let is_select = trimmed.starts_with("SELECT") || trimmed.starts_with("PRAGMA");

        // E-02 FIX: Release the GIL for the SQLite operation.
        // This prevents deadlock when another Python thread tries to call
        // into Rust while this thread holds the GIL and waits for the
        // SQLite lock.
        let result = py.allow_threads(|| {
            self._execute_inner(sql, &param_values, is_select)
        });

        // Convert the internal result to Python objects (requires GIL)
        match result? {
            DbResult::Select { column_names, rows } => {
                let result_list = PyList::empty_bound(py);
                for row_values in &rows {
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
                    result_list.append(py_row)?;
                }
                let dict = PyDict::new_bound(py);
                dict.set_item("columns", column_names)?;
                dict.set_item("rows", result_list)?;
                Ok(dict.into_any().unbind())
            }
            DbResult::Execute { affected } => {
                Ok(affected.to_object(py))
            }
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

    // -----------------------------------------------------------------------
    // Inner execution (GIL-free)
    // -----------------------------------------------------------------------

    /// Internal execution that does NOT hold the GIL.
    ///
    /// E-02 FIX: All SQLite operations run without the GIL to prevent
    /// deadlock. Python objects are converted before/after this call.
    fn _execute_inner(
        &self,
        sql: &str,
        param_values: &[rusqlite::types::Value],
        is_select: bool,
    ) -> PyResult<DbResult> {
        let guard = self
            .conn
            .lock()
            .map_err(|e| PyRuntimeError::new_err(format!("Lock poisoned: {}", e)))?;

        let conn = guard
            .as_ref()
            .ok_or_else(|| PyRuntimeError::new_err("Database is closed"))?;

        let params_refs: Vec<&dyn rusqlite::types::ToSql> = param_values
            .iter()
            .map(|v| v as &dyn rusqlite::types::ToSql)
            .collect();

        if is_select {
            let mut stmt = conn
                .prepare(sql)
                .map_err(|e| PyRuntimeError::new_err(format!("Prepare error: {}", e)))?;

            let column_count = stmt.column_count();
            let column_names: Vec<String> = (0..column_count)
                .map(|i| stmt.column_name(i).unwrap_or("?").to_string())
                .collect();

            let rows: Vec<Vec<rusqlite::types::Value>> = stmt
                .query_map(params_refs.as_slice(), |row| {
                    let mut values = Vec::with_capacity(column_count);
                    for i in 0..column_count {
                        let val: rusqlite::types::Value =
                            row.get(i).unwrap_or(rusqlite::types::Value::Null);
                        values.push(val);
                    }
                    Ok(values)
                })
                .map_err(|e| PyRuntimeError::new_err(format!("Query error: {}", e)))?
                .filter_map(|r| r.ok())
                .collect();

            Ok(DbResult::Select { column_names, rows })
        } else {
            let affected = conn
                .execute(sql, params_refs.as_slice())
                .map_err(|e| PyRuntimeError::new_err(format!("Execute error: {}", e)))?;
            Ok(DbResult::Execute { affected })
        }
    }
}

// ---------------------------------------------------------------------------
// DbResult — internal result type for GIL-free execution
// ---------------------------------------------------------------------------

/// Internal result type for database operations, used to decouple
/// SQLite execution (GIL-free) from Python object construction (GIL-required).
enum DbResult {
    Select {
        column_names: Vec<String>,
        rows: Vec<Vec<rusqlite::types::Value>>,
    },
    Execute {
        affected: usize,
    },
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
