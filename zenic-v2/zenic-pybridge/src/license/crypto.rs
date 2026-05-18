//! Cryptographic primitives — HMAC-SHA256, constant-time comparison, hex encode/decode.

use hmac::Hmac;
use sha2::Sha256;

/// Constant-time comparison of two byte slices.
pub(crate) fn constant_time_compare(a: &[u8], b: &[u8]) -> bool {
    if a.len() != b.len() {
        return false;
    }
    let mut result: u8 = 0;
    for (x, y) in a.iter().zip(b.iter()) {
        result |= x ^ y;
    }
    result == 0
}

/// Compute HMAC-SHA256 of data with the given secret key.
pub(crate) fn hmac_sha256(secret: &[u8], data: &[u8]) -> [u8; 32] {
    use hmac::Mac;
    let mut mac = Hmac::<Sha256>::new_from_slice(secret)
        .expect("HMAC can accept any key size");
    mac.update(data);
    mac.finalize().into_bytes().into()
}

/// Encode bytes as a hex string (lowercase).
pub(crate) fn hex_encode(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{:02x}", b)).collect()
}

/// Decode a hex string to bytes.
pub(crate) fn hex_decode(hex: &str) -> Result<Vec<u8>, String> {
    let hex = hex.trim();
    if hex.len() % 2 != 0 {
        return Err("Hex string has odd length".to_string());
    }
    (0..hex.len())
        .step_by(2)
        .map(|i| {
            u8::from_str_radix(&hex[i..i + 2], 16)
                .map_err(|e| format!("Invalid hex at position {}: {}", i, e))
        })
        .collect()
}
