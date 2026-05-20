//! Kill-switch connectivity check — TCP with timeout + grace period.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use std::io::Read;
use std::net::TcpStream;
use std::time::Duration;

/// Parse a URL string to extract (host, port).
pub(crate) fn parse_host_port(url: &str) -> Option<(String, u16)> {
    let url = url.trim();
    if url.is_empty() {
        return None;
    }

    let (scheme, rest) = if url.starts_with("https://") {
        ("https", &url[8..])
    } else if url.starts_with("http://") {
        ("http", &url[7..])
    } else {
        ("http", url)
    };

    let host_port = rest.split('/').next().unwrap_or(rest);
    let default_port: u16 = if scheme == "https" { 443 } else { 80 };

    // Handle [IPv6]:port format
    if host_port.starts_with('[') {
        if let Some(bracket_end) = host_port.find(']') {
            let host = &host_port[1..bracket_end];
            let remainder = &host_port[bracket_end + 1..];
            let port = if remainder.starts_with(':') {
                remainder[1..].parse().unwrap_or(default_port)
            } else {
                default_port
            };
            return Some((host.to_string(), port));
        }
    }

    // Handle host:port format
    if let Some(colon_pos) = host_port.rfind(':') {
        let host = &host_port[..colon_pos];
        let port_str = &host_port[colon_pos + 1..];
        if port_str.chars().all(|c| c.is_ascii_digit()) && !port_str.is_empty() {
            let port = port_str.parse().unwrap_or(default_port);
            return Some((host.to_string(), port));
        }
    }

    Some((host_port.to_string(), default_port))
}

/// Perform a simple HTTP GET request over an established TCP stream.
fn perform_simple_http_get(
    stream: &TcpStream,
    host: &str,
    path_url: &str,
    license_key: &str,
    timeout: Duration,
) -> Result<String, std::io::Error> {
    use std::io::{BufRead, BufReader, Write};

    stream.set_read_timeout(Some(timeout))?;
    stream.set_write_timeout(Some(timeout))?;

    // Extract path from URL
    let path = if path_url.starts_with("http://") || path_url.starts_with("https://") {
        let after_scheme = if path_url.starts_with("http://") {
            &path_url[7..]
        } else {
            &path_url[8..]
        };
        if let Some(slash_pos) = after_scheme.find('/') {
            &after_scheme[slash_pos..]
        } else {
            "/"
        }
    } else {
        "/"
    };

    let request = format!(
        "GET {}?license_key={} HTTP/1.1\r\nHost: {}\r\nConnection: close\r\nAccept: application/json\r\n\r\n",
        path, license_key, host
    );

    let mut stream = stream.try_clone()?;
    stream.write_all(request.as_bytes())?;

    let mut reader = BufReader::new(stream);
    let mut body = String::new();

    // Skip HTTP headers
    loop {
        let mut line = String::new();
        match reader.read_line(&mut line) {
            Ok(0) | Err(_) => break,
            Ok(_) => {
                if line == "\r\n" || line == "\n" {
                    break;
                }
            }
        }
    }

    reader.read_to_string(&mut body)?;
    Ok(body)
}

/// Check the remote kill-switch endpoint.
///
/// Performs a TCP connectivity check to the remote URL. If the server is
/// reachable, attempts a minimal HTTP GET to read the response. If the
/// server is unreachable, a grace period is applied.
///
/// Parameters
/// ----------
/// remote_url : str
///     The kill-switch endpoint URL.
/// license_key : str
///     The license key to identify the client.
/// timeout_secs : int
///     Connection timeout in seconds (default: 5).
///
/// Returns
/// -------
/// dict
///     ``{"is_active": bool, "should_disable": bool, "message": str}``
#[pyfunction]
#[pyo3(signature = (remote_url, license_key, timeout_secs=5u64))]
pub fn check_kill_switch(
    py: Python<'_>,
    remote_url: &str,
    license_key: &str,
    timeout_secs: u64,
) -> PyResult<Py<PyDict>> {
    let result = PyDict::new_bound(py);

    // Empty URL = no kill switch configured
    if remote_url.trim().is_empty() {
        result.set_item("is_active", true)?;
        result.set_item("should_disable", false)?;
        result.set_item("message", "No kill switch URL configured, license is active")?;
        return Ok(result.unbind());
    }

    // Parse the URL to extract host and port
    let (host, port) = match parse_host_port(remote_url) {
        Some(hp) => hp,
        None => {
            result.set_item("is_active", false)?;
            result.set_item("should_disable", false)?;
            result.set_item("message", format!("Invalid kill switch URL: {}", remote_url))?;
            return Ok(result.unbind());
        }
    };

    // Try TCP connection with timeout
    let addr = format!("{}:{}", host, port);
    let timeout = Duration::from_secs(timeout_secs);

    match TcpStream::connect_timeout(
        &addr.parse().map_err(|e: std::net::AddrParseError| {
            PyValueError::new_err(format!("Invalid address '{}': {}", addr, e))
        })?,
        timeout,
    ) {
        Ok(stream) => {
            // Server is reachable — attempt a minimal HTTP GET
            let response = perform_simple_http_get(
                &stream, &host, remote_url, license_key, timeout,
            );

            match response {
                Ok(body) => {
                    if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&body) {
                        let is_active = parsed
                            .get("active")
                            .or_else(|| parsed.get("is_active"))
                            .and_then(|v| v.as_bool())
                            .unwrap_or(true);

                        let should_disable = parsed
                            .get("should_disable")
                            .and_then(|v| v.as_bool())
                            .unwrap_or(false);

                        let message = parsed
                            .get("message")
                            .and_then(|v| v.as_str())
                            .unwrap_or("Kill switch check completed")
                            .to_string();

                        result.set_item("is_active", is_active)?;
                        result.set_item("should_disable", should_disable)?;
                        result.set_item("message", message)?;
                    } else {
                        result.set_item("is_active", true)?;
                        result.set_item("should_disable", false)?;
                        result.set_item("message", "Server reachable, license appears active")?;
                    }
                }
                Err(_) => {
                    result.set_item("is_active", true)?;
                    result.set_item("should_disable", false)?;
                    result.set_item(
                        "message",
                        "Server reachable but could not read response, license assumed active",
                    )?;
                }
            }
        }
        Err(_) => {
            // Server unreachable — apply grace period
            result.set_item("is_active", false)?;
            result.set_item("should_disable", false)?;
            result.set_item(
                "message",
                format!("Kill switch server unreachable ({}), grace period active", addr),
            )?;
        }
    }

    Ok(result.unbind())
}
