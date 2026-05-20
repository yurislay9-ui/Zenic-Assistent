//! Unit tests for the forensic module.

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_forensic_hash_deterministic() {
        let a = super::super::hashing::forensic_hash(
            "id1", "tenant1", "CREATE", "desc", "actor", "2024-01-01", "{}",
        ).unwrap();
        let b = super::super::hashing::forensic_hash(
            "id1", "tenant1", "CREATE", "desc", "actor", "2024-01-01", "{}",
        ).unwrap();
        assert_eq!(a, b);
    }

    #[test]
    fn test_forensic_hash_different_inputs() {
        let a = super::super::hashing::forensic_hash(
            "id1", "tenant1", "CREATE", "desc", "actor", "2024-01-01", "{}",
        ).unwrap();
        let b = super::super::hashing::forensic_hash(
            "id2", "tenant1", "CREATE", "desc", "actor", "2024-01-01", "{}",
        ).unwrap();
        assert_ne!(a, b);
    }

    #[test]
    fn test_chain_hash_basic() {
        let result = super::super::hashing::chain_hash("parent123", "entry456").unwrap();
        assert_eq!(result.len(), 64);
    }

    #[test]
    fn test_chain_hash_genesis() {
        // Genesis entries have empty parent
        let result = super::super::hashing::chain_hash("", "entry456").unwrap();
        assert_eq!(result.len(), 64);
    }

    #[test]
    fn test_forensic_hash_empty_id_error() {
        assert!(super::super::hashing::forensic_hash("", "t", "e", "d", "a", "ts", "{}").is_err());
    }

    #[test]
    fn test_build_merkle_tree_with_proof_single() {
        let leaves = vec!["hash1".to_string()];
        let (root, proof) = super::super::merkle::build_merkle_tree_with_proof(&leaves, 0);
        assert!(proof.is_empty());
        assert!(!root.is_empty());
    }

    #[test]
    fn test_build_merkle_tree_with_proof_multi() {
        let leaves = vec![
            "hash1".to_string(),
            "hash2".to_string(),
            "hash3".to_string(),
            "hash4".to_string(),
        ];
        let (root, proof) = super::super::merkle::build_merkle_tree_with_proof(&leaves, 0);
        assert_eq!(proof.len(), 2); // log2(4) = 2 levels
        assert!(super::super::merkle::verify_merkle_proof("hash1", 0, &proof, &root));
    }

    #[test]
    fn test_verify_merkle_proof_tampered() {
        let leaves = vec![
            "hash1".to_string(),
            "hash2".to_string(),
            "hash3".to_string(),
            "hash4".to_string(),
        ];
        let (root, proof) = super::super::merkle::build_merkle_tree_with_proof(&leaves, 0);
        assert!(!super::super::merkle::verify_merkle_proof("tampered", 0, &proof, &root));
    }
}
