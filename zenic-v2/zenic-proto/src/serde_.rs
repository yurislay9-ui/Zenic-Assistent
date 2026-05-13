//! Serialization utilities for Zenic-Agents.
//!
//! All persistent state uses bincode for speed and zstd for compression.
//! This is the canonical encode/decode pair used across all crates.

use crate::errors::ProtoError;
use serde::{Deserialize, Serialize};

/// Compression level used for zstd encoding.
/// Level 3 offers a good balance between speed and ratio.
const ZSTD_COMPRESSION_LEVEL: i32 = 3;

/// Serialize and compress a value using bincode + zstd.
///
/// This is the primary on-disk format for subgraphs and checkpoints.
/// The encoding is: `[4 bytes: uncompressed size (LE u32)] [zstd-compressed bincode payload]`.
pub fn encode<T: Serialize>(val: &T) -> Result<Vec<u8>, ProtoError> {
    let raw = bincode::serialize(val).map_err(|e| ProtoError::Serialization(e.to_string()))?;
    let uncompressed_len = u32::try_from(raw.len())
        .map_err(|_| ProtoError::Compression("payload exceeds 4 GB".to_string()))?;

    let mut out = Vec::with_capacity(raw.len() / 2 + 8);
    out.extend_from_slice(&uncompressed_len.to_le_bytes());

    zstd::encode_all(&raw[..], ZSTD_COMPRESSION_LEVEL)
        .map(|compressed| {
            out.extend_from_slice(&compressed);
            out
        })
        .map_err(|e| ProtoError::Compression(e.to_string()))
}

/// Decompress and deserialize a value using zstd + bincode.
///
/// Expects the format produced by [`encode`]:
/// `[4 bytes: uncompressed size (LE u32)] [zstd-compressed bincode payload]`.
pub fn decode<T: for<'de> Deserialize<'de>>(data: &[u8]) -> Result<T, ProtoError> {
    if data.len() < 4 {
        return Err(ProtoError::Deserialization(
            "payload too short: missing size header".to_string(),
        ));
    }

    let size_bytes: [u8; 4] = data[..4]
        .try_into()
        .map_err(|_| ProtoError::Deserialization("invalid size header".to_string()))?;
    let _expected_len = u32::from_le_bytes(size_bytes) as usize;

    let decompressed = zstd::decode_all(&data[4..])
        .map_err(|e| ProtoError::Decompression(e.to_string()))?;

    bincode::deserialize(&decompressed).map_err(|e| ProtoError::Deserialization(e.to_string()))
}

/// Serialize a value using bincode only (no compression).
/// Useful for small, transient payloads where compression overhead is wasteful.
pub fn encode_raw<T: Serialize>(val: &T) -> Result<Vec<u8>, ProtoError> {
    bincode::serialize(val).map_err(|e| ProtoError::Serialization(e.to_string()))
}

/// Deserialize a value from raw bincode (no compression).
pub fn decode_raw<T: for<'de> Deserialize<'de>>(data: &[u8]) -> Result<T, ProtoError> {
    bincode::deserialize(data).map_err(|e| ProtoError::Deserialization(e.to_string()))
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[derive(Debug, PartialEq, Serialize, Deserialize)]
    struct TestPayload {
        name: String,
        value: u64,
    }

    #[test]
    fn encode_decode_roundtrip() {
        let original = TestPayload {
            name: "inventory_check".to_string(),
            value: 42,
        };
        let encoded = encode(&original).expect("encode");
        let decoded: TestPayload = decode(&encoded).expect("decode");
        assert_eq!(original, decoded);
    }

    #[test]
    fn encode_raw_decode_raw_roundtrip() {
        let original = TestPayload {
            name: "raw_test".to_string(),
            value: 99,
        };
        let encoded = encode_raw(&original).expect("encode_raw");
        let decoded: TestPayload = decode_raw(&encoded).expect("decode_raw");
        assert_eq!(original, decoded);
    }

    #[test]
    fn encoded_is_smaller_than_raw() {
        let payload = vec![0u8; 1024]; // Compressible data
        let compressed = encode(&payload).expect("encode");
        let raw = encode_raw(&payload).expect("encode_raw");
        assert!(compressed.len() < raw.len());
    }

    #[test]
    fn decode_empty_returns_error() {
        let result: Result<Vec<u8>, ProtoError> = decode(&[]);
        assert!(result.is_err());
    }

    #[test]
    fn decode_garbage_returns_error() {
        let result: Result<Vec<u8>, ProtoError> = decode(&[0xFF, 0xFF, 0xFF, 0xFF, 0x00]);
        assert!(result.is_err());
    }

    #[test]
    fn decode_raw_garbage_returns_error() {
        let result: Result<Vec<u8>, ProtoError> = decode_raw(&[0xDE, 0xAD]);
        assert!(result.is_err());
    }
}
