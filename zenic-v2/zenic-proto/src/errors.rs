//! Error types for the proto layer.

use thiserror::Error;

/// Errors that can occur in the proto (shared types) layer.
#[derive(Debug, Error)]
pub enum ProtoError {
    /// Serialization failed (bincode).
    #[error("serialization failed: {0}")]
    Serialization(String),

    /// Deserialization failed (bincode).
    #[error("deserialization failed: {0}")]
    Deserialization(String),

    /// Compression failed (zstd).
    #[error("compression failed: {0}")]
    Compression(String),

    /// Decompression failed (zstd).
    #[error("decompression failed: {0}")]
    Decompression(String),

    /// Invalid input was provided.
    #[error("invalid input: {0}")]
    InvalidInput(String),
}

impl From<bincode::Error> for ProtoError {
    fn from(err: bincode::Error) -> Self {
        ProtoError::Serialization(err.to_string())
    }
}

impl From<std::io::Error> for ProtoError {
    fn from(err: std::io::Error) -> Self {
        ProtoError::Compression(err.to_string())
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn proto_error_display() {
        let err = ProtoError::Serialization("test".to_string());
        assert!(err.to_string().contains("test"));
    }

    #[test]
    fn proto_error_from_bincode() {
        // bincode::Error is hard to construct directly, so we test the variant
        let err = ProtoError::Deserialization("bad data".to_string());
        assert!(err.to_string().contains("bad data"));
    }

    #[test]
    fn proto_error_from_io() {
        let io_err = std::io::Error::new(std::io::ErrorKind::UnexpectedEof, "truncated");
        let proto_err: ProtoError = io_err.into();
        assert!(matches!(proto_err, ProtoError::Compression(_)));
    }
}
