//! LRU Memory Cache for the hot path (<1μs lookup).
//!
//! Uses bincode-serialized [`SemanticMapping`] entries for fast access.
//! The cache is backed by a [`HashMap`] with `RwLock` for concurrent
//! read access. rkyv zero-copy optimization is planned for future use
//! once cross-crate `NodeId` gains rkyv support.
//!
//! ## Eviction Policy
//!
//! When the cache reaches `max_size`, the bottom 10% of entries (by access
//! count) are evicted. This is a simple approximation of LRU that avoids
//! the overhead of maintaining a full doubly-linked list.
//!
//! ## Tier-Based Sizing
//!
//! The cache can be created with [`MemoryCache::new_for_tier`] which
//! automatically selects the maximum size based on the subscription tier's
//! feature gate limits.

use std::collections::HashMap;
use std::sync::RwLock;

use crate::errors::MemoryError;
use crate::types::{FeatureGate, SemanticMapping, SubscriptionTier};

// ---------------------------------------------------------------------------
// CacheEntry
// ---------------------------------------------------------------------------

/// LRU cache entry with pre-serialized mapping for fast access.
///
/// The `serialized_bytes` field is pre-serialized at insert time so that
/// lookups can access the mapping data with minimal overhead.
/// Currently uses bincode; rkyv zero-copy optimization is planned
/// once cross-crate `NodeId` gains rkyv support.
struct CacheEntry {
    /// The deserialized mapping (for direct access).
    mapping: SemanticMapping,
    /// Pre-serialized with bincode for fast re-serialization.
    /// Reserved for future network-transfer optimization.
    #[allow(dead_code)]
    serialized_bytes: Vec<u8>,
    /// Number of times this entry has been accessed (for LRU eviction).
    access_count: u64,
}

// ---------------------------------------------------------------------------
// MemoryCache
// ---------------------------------------------------------------------------

/// LRU cache backed by HashMap with configurable size per subscription tier.
///
/// # Thread Safety
///
/// The cache uses `RwLock` internally, allowing multiple concurrent readers
/// but exclusive write access. This is optimized for the read-heavy pattern
/// of semantic lookups.
///
/// # Example
///
/// ```ignore
/// use zenic_memory::{MemoryCache, SemanticMapping, LearningMechanism};
///
/// let cache = MemoryCache::new(1000);
///
/// let mapping = SemanticMapping::new(
///     "map-001".to_string(),
///     "cobro".to_string(),
///     "synonym_of".to_string(),
///     "factura".to_string(),
///     LearningMechanism::SchemaDrift,
/// );
///
/// cache.insert("cobro", &mapping, "tenant-1")?;
/// let found = cache.lookup("cobro", "tenant-1");
/// assert!(found.is_some());
/// ```
pub struct MemoryCache {
    /// The cache entries, protected by a read-write lock.
    entries: RwLock<HashMap<String, CacheEntry>>,
    /// Maximum number of entries before eviction kicks in.
    max_size: usize,
    /// Per-tenant entry counts for quota tracking.
    tenant_sizes: RwLock<HashMap<String, usize>>,
}

impl MemoryCache {
    /// Creates a new cache with the given maximum number of entries.
    ///
    /// When the cache reaches `max_size`, the least recently used entries
    /// will be evicted to make room for new insertions.
    pub fn new(max_size: usize) -> Self {
        Self {
            entries: RwLock::new(HashMap::with_capacity(max_size)),
            max_size,
            tenant_sizes: RwLock::new(HashMap::new()),
        }
    }

    /// Creates a new cache with tier-appropriate size using [`SubscriptionTier`].
    ///
    /// The maximum number of entries is determined by
    /// [`FeatureGate::for_tier`] which maps the tier to its LRU cache size.
    pub fn new_for_tier(tier: SubscriptionTier) -> Self {
        Self::new(FeatureGate::for_tier(tier).lru_cache_size)
    }

    /// Hot path lookup (<1μs target).
    ///
    /// Returns a clone of the [`SemanticMapping`] if found, or `None`.
    /// The access count is incremented for LRU tracking.
    pub fn lookup(&self, origin: &str, tenant_id: &str) -> Option<SemanticMapping> {
        let key = Self::make_key(origin, tenant_id);
        let mut entries = self.entries.write().ok()?;
        entries.get_mut(&key).map(|entry| {
            entry.access_count += 1;
            entry.mapping.clone()
        })
    }

    /// Inserts a mapping into the cache with bincode pre-serialization.
    ///
    /// If the cache is full, the least recently used entries (bottom 10%
    /// by access count) are evicted before insertion.
    pub fn insert(
        &self,
        origin: &str,
        mapping: &SemanticMapping,
        tenant_id: &str,
    ) -> Result<(), MemoryError> {
        let key = Self::make_key(origin, tenant_id);

        // Pre-serialize with bincode for fast re-serialization.
        // rkyv zero-copy optimization is planned for future use once
        // cross-crate types (NodeId) gain rkyv support.
        let serialized_bytes = bincode::serialize(mapping)
            .map_err(|e| MemoryError::SerializationError(e.to_string()))?;

        let mut entries = self.entries.write().map_err(|e| {
            MemoryError::Internal(format!("cache write lock poisoned: {}", e))
        })?;

        // Evict if we're at capacity and this is a new key.
        if entries.len() >= self.max_size && !entries.contains_key(&key) {
            evict_lru(&mut entries, self.max_size / 10);
        }

        // Track tenant size.
        if !entries.contains_key(&key) {
            if let Ok(mut tenant_sizes) = self.tenant_sizes.write() {
                *tenant_sizes.entry(tenant_id.to_string()).or_insert(0) += 1;
            }
        }

        entries.insert(
            key,
            CacheEntry {
                mapping: mapping.clone(),
                serialized_bytes,
                access_count: 0,
            },
        );

        Ok(())
    }

    /// Removes an entry from the cache.
    pub fn remove(&self, origin: &str, tenant_id: &str) {
        let key = Self::make_key(origin, tenant_id);
        if let Ok(mut entries) = self.entries.write() {
            if entries.remove(&key).is_some() {
                if let Ok(mut tenant_sizes) = self.tenant_sizes.write() {
                    if let Some(count) = tenant_sizes.get_mut(tenant_id) {
                        *count = count.saturating_sub(1);
                    }
                }
            }
        }
    }

    /// Clears all entries from the cache.
    pub fn clear(&self) {
        if let Ok(mut entries) = self.entries.write() {
            entries.clear();
        }
        if let Ok(mut tenant_sizes) = self.tenant_sizes.write() {
            tenant_sizes.clear();
        }
    }

    /// Returns the current number of entries in the cache.
    pub fn len(&self) -> usize {
        self.entries.read().map(|e| e.len()).unwrap_or(0)
    }

    /// Returns true if the cache is empty.
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// Returns the maximum number of entries the cache can hold.
    pub fn max_size(&self) -> usize {
        self.max_size
    }

    /// Returns the number of entries for a specific tenant.
    pub fn tenant_len(&self, tenant_id: &str) -> usize {
        self.tenant_sizes
            .read()
            .map(|t| *t.get(tenant_id).unwrap_or(&0))
            .unwrap_or(0)
    }

    /// Constructs the composite cache key from origin and tenant_id.
    ///
    /// Format: `"{tenant_id}::{origin}"`
    pub fn make_key(origin: &str, tenant_id: &str) -> String {
        format!("{}::{}", tenant_id, origin)
    }
}

// ---------------------------------------------------------------------------
// Eviction
// ---------------------------------------------------------------------------

/// Evicts the bottom `count` entries by access count (simple LRU approximation).
///
/// This is a simple approach: collect all keys sorted by access count
/// ascending, then remove the first `count` entries.
fn evict_lru(entries: &mut HashMap<String, CacheEntry>, count: usize) {
    if count == 0 || entries.is_empty() {
        return;
    }

    // Collect (key, access_count) pairs.
    let mut access_counts: Vec<(String, u64)> = entries
        .iter()
        .map(|(k, v)| (k.clone(), v.access_count))
        .collect();

    // Sort by access count ascending (least accessed first).
    access_counts.sort_by_key(|(_, count)| *count);

    // Evict the bottom `count` entries.
    let to_evict = access_counts.into_iter().take(count);
    for (key, _) in to_evict {
        entries.remove(&key);
    }
}

// ---------------------------------------------------------------------------
// Default
// ---------------------------------------------------------------------------

impl Default for MemoryCache {
    fn default() -> Self {
        Self::new(1_000)
    }
}
