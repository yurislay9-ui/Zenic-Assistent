"""
Unit tests for Level 7 - Merkle Ledger

Tests for snapshot, commit, rollback, and hash chain integrity.
"""

import pytest
from pathlib import Path
from src.core.level7_merkle_ledger.ledger import MerkleLedger


@pytest.fixture
def ledger():
    return MerkleLedger()


class TestMerkleLedger:
    """Tests for the MerkleLedger class."""

    def test_hash_content_deterministic(self, ledger):
        """Content hashing should be deterministic."""
        h1 = ledger._hash_content("hello world")
        h2 = ledger._hash_content("hello world")
        assert h1 == h2

    def test_hash_content_different(self, ledger):
        """Different content should produce different hashes."""
        h1 = ledger._hash_content("hello")
        h2 = ledger._hash_content("world")
        assert h1 != h2

    def test_merkle_root_empty(self, ledger):
        """Empty hash list should return a default root."""
        root = ledger._merkle_root([])
        assert root is not None
        assert len(root) == 64  # SHA256 hex

    def test_merkle_root_single(self, ledger):
        """Single hash should be its own root."""
        h = ledger._hash_content("test")
        root = ledger._merkle_root([h])
        assert root == h

    def test_merkle_root_two_hashes(self, ledger):
        """Two hashes should combine correctly."""
        h1 = ledger._hash_content("left")
        h2 = ledger._hash_content("right")
        root = ledger._merkle_root([h1, h2])
        assert root != h1
        assert root != h2
        assert len(root) == 64

    def test_merkle_root_even_count(self, ledger):
        """Should handle even number of hashes."""
        hashes = [ledger._hash_content(f"node{i}") for i in range(4)]
        root = ledger._merkle_root(hashes)
        assert len(root) == 64

    def test_merkle_root_odd_count(self, ledger):
        """Should handle odd number of hashes (duplicates last)."""
        hashes = [ledger._hash_content(f"node{i}") for i in range(3)]
        root = ledger._merkle_root(hashes)
        assert len(root) == 64

    def test_commit_returns_merkle_node(self, ledger):
        """Commit should return a MerkleNode with hash chain."""
        node = ledger.commit("test.py", "content here", "/tmp")
        assert node.hash_sha256 is not None
        assert node.parent_hash is not None
        assert node.operation == "COMMIT"

    def test_commit_creates_hash_chain(self, ledger):
        """Multiple commits should create a hash chain."""
        node1 = ledger.commit("test.py", "version 1", "/tmp")
        node2 = ledger.commit("test.py", "version 2", "/tmp")
        # Second commit should reference first
        assert node2.parent_hash != "GENESIS"

    def test_get_last_hash_genesis(self, ledger):
        """Should return GENESIS for unknown files."""
        h = ledger._get_last_hash("nonexistent_file.py")
        assert h == "GENESIS"
