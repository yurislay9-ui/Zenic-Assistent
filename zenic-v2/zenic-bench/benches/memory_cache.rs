//! Benchmarks for `MemoryCache` — the LRU hot-path cache.
//!
//! The cache backs semantic lookups with a `HashMap<String, CacheEntry>` protected
//! by an `RwLock`.  These benchmarks measure the cost of the three fundamental
//! operations (lookup-hit, lookup-miss, insert) plus eviction and concurrent
//! read throughput, parameterised across cache sizes that match the subscription
//! tier limits (100 = Starter, 500 = Business, 2000 = Enterprise).

use criterion::{
    black_box, criterion_group, criterion_main, BenchmarkId, Criterion, Throughput,
};
use std::sync::Arc;
use std::thread;

use zenic_memory::{LearningMechanism, MemoryCache, SemanticMapping};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Creates a small `SemanticMapping` suitable for cache insertion.
///
/// "Small" means short string fields so that the serialised bincode payload
/// is minimal — this isolates the benchmark from serialisation overhead.
fn make_small_mapping(id: usize) -> SemanticMapping {
    SemanticMapping::new(
        format!("map-{id}"),
        format!("origin-{id}"),
        "synonym_of".to_string(),
        format!("dest-{id}"),
        LearningMechanism::SchemaDrift,
    )
}

/// Creates a large `SemanticMapping` with long string fields.
///
/// The extra payload length stresses both the bincode serialisation in
/// `MemoryCache::insert` and the memory footprint of the cache.
fn make_large_mapping(id: usize) -> SemanticMapping {
    let long_origin = "x".repeat(1024);
    let long_dest = "y".repeat(1024);
    SemanticMapping::new(
        format!("map-large-{id}"),
        format!("{long_origin}-{id}"),
        "synonym_of".to_string(),
        format!("{long_dest}-{id}"),
        LearningMechanism::IntentRouting,
    )
}

/// Pre-populates a cache with `count` entries under a single tenant.
fn populate_cache(cache: &MemoryCache, count: usize, tenant: &str) {
    for i in 0..count {
        let mapping = make_small_mapping(i);
        let _ = cache.insert(&format!("origin-{i}"), &mapping, tenant);
    }
}

// ---------------------------------------------------------------------------
// Benchmark: lookup_hit
// ---------------------------------------------------------------------------

/// Measures the time to look up a key that exists in the cache.
///
/// This is the hot-path operation — the cache design targets <1 µs per
/// hit.  We measure across different cache sizes to verify that the O(1)
/// HashMap lookup stays constant regardless of entry count.
fn bench_lookup_hit(c: &mut Criterion) {
    let mut group = c.benchmark_group("memory_cache/lookup_hit");

    for &size in &[100usize, 500, 2000] {
        let cache = MemoryCache::new(size);
        let tenant = "tenant-hit";
        populate_cache(&cache, size, tenant);

        group.throughput(Throughput::Elements(1));
        group.bench_with_input(
            BenchmarkId::new("cache_size", size),
            &cache,
            |b, cache| {
                // Rotate through keys so we don't always hit the same entry
                let mut idx = 0;
                b.iter(|| {
                    let key = format!("origin-{}", idx % size);
                    let result = cache.lookup(black_box(&key), black_box(tenant));
                    debug_assert!(result.is_some());
                    idx += 1;
                });
            },
        );
    }

    group.finish();
}

// ---------------------------------------------------------------------------
// Benchmark: lookup_miss
// ---------------------------------------------------------------------------

/// Measures the time to look up a key that does NOT exist in the cache.
///
/// A miss only needs the HashMap `get` to return `None`, so this should be
/// slightly faster than a hit (no clone, no access-count increment).  Still
/// useful to confirm the RwLock acquisition overhead on the miss path.
fn bench_lookup_miss(c: &mut Criterion) {
    let mut group = c.benchmark_group("memory_cache/lookup_miss");

    for &size in &[100usize, 500, 2000] {
        let cache = MemoryCache::new(size);
        let tenant = "tenant-miss";
        populate_cache(&cache, size, tenant);

        group.throughput(Throughput::Elements(1));
        group.bench_with_input(
            BenchmarkId::new("cache_size", size),
            &cache,
            |b, cache| {
                let mut idx = 0;
                b.iter(|| {
                    // Keys that were never inserted
                    let key = format!("missing-{idx}");
                    let result = cache.lookup(black_box(&key), black_box(tenant));
                    debug_assert!(result.is_none());
                    idx += 1;
                });
            },
        );
    }

    group.finish();
}

// ---------------------------------------------------------------------------
// Benchmark: insert_small
// ---------------------------------------------------------------------------

/// Measures the time to insert a small mapping into the cache.
///
/// Small mappings have short string fields, so the bincode serialisation
/// cost is minimal.  This isolates the HashMap insert + RwLock write-lock
/// overhead.
fn bench_insert_small(c: &mut Criterion) {
    let mut group = c.benchmark_group("memory_cache/insert_small");

    for &size in &[100usize, 500, 2000] {
        group.throughput(Throughput::Elements(1));
        group.bench_with_input(
            BenchmarkId::new("cache_size", size),
            &size,
            |b, &size| {
                let cache = MemoryCache::new(size);
                let tenant = "tenant-insert-small";
                let mut idx = 0;
                b.iter(|| {
                    let mapping = make_small_mapping(idx);
                    cache
                        .insert(black_box(&format!("origin-{idx}")), black_box(&mapping), black_box(tenant))
                        .unwrap();
                    idx += 1;
                });
            },
        );
    }

    group.finish();
}

// ---------------------------------------------------------------------------
// Benchmark: insert_large
// ---------------------------------------------------------------------------

/// Measures the time to insert a large mapping into the cache.
///
/// Large mappings contain 1 KiB string fields, making the bincode
/// serialisation cost dominate over the HashMap insert itself.  This helps
/// quantify the serialisation overhead in `MemoryCache::insert`.
fn bench_insert_large(c: &mut Criterion) {
    let mut group = c.benchmark_group("memory_cache/insert_large");

    for &size in &[100usize, 500, 2000] {
        group.throughput(Throughput::Elements(1));
        group.bench_with_input(
            BenchmarkId::new("cache_size", size),
            &size,
            |b, &size| {
                let cache = MemoryCache::new(size);
                let tenant = "tenant-insert-large";
                let mut idx = 0;
                b.iter(|| {
                    let mapping = make_large_mapping(idx);
                    cache
                        .insert(black_box(&format!("origin-{idx}")), black_box(&mapping), black_box(tenant))
                        .unwrap();
                    idx += 1;
                });
            },
        );
    }

    group.finish();
}

// ---------------------------------------------------------------------------
// Benchmark: eviction
// ---------------------------------------------------------------------------

/// Measures the cost of inserting into a full cache, which triggers eviction.
///
/// When the cache reaches `max_size`, the bottom 10% of entries (by access
/// count) are evicted before the new entry can be inserted.  This benchmark
/// pre-fills the cache to capacity and then measures the insert that causes
/// eviction, capturing the full sort + remove cycle.
fn bench_eviction(c: &mut Criterion) {
    let mut group = c.benchmark_group("memory_cache/eviction");

    for &size in &[100usize, 500, 2000] {
        group.throughput(Throughput::Elements(1));
        group.bench_with_input(
            BenchmarkId::new("cache_size", size),
            &size,
            |b, &size| {
                let tenant = "tenant-evict";
                let mut idx = 0;
                b.iter(|| {
                    // Fresh cache for each iteration
                    let cache = MemoryCache::new(size);
                    populate_cache(&cache, size, tenant);

                    // This insert triggers eviction (cache is at max_size)
                    let mapping = make_small_mapping(size + idx);
                    cache
                        .insert(
                            black_box(&format!("origin-{}", size + idx)),
                            black_box(&mapping),
                            black_box(tenant),
                        )
                        .unwrap();
                    idx += 1;
                });
            },
        );
    }

    group.finish();
}

// ---------------------------------------------------------------------------
// Benchmark: concurrent_read
// ---------------------------------------------------------------------------

/// Measures concurrent read throughput with multiple threads.
///
/// The `RwLock` allows multiple readers simultaneously.  This benchmark
/// spawns several threads that each perform lookups on a shared cache to
/// verify that the lock doesn't degrade read throughput under contention.
fn bench_concurrent_read(c: &mut Criterion) {
    let mut group = c.benchmark_group("memory_cache/concurrent_read");

    for &size in &[100usize, 500, 2000] {
        let cache = Arc::new(MemoryCache::new(size));
        let tenant = "tenant-concurrent";
        populate_cache(&cache, size, tenant);

        for &num_threads in &[1usize, 2, 4] {
            group.throughput(Throughput::Elements(num_threads as u64 * 1000));
            group.bench_with_input(
                BenchmarkId::new(format!("size_{size}"), num_threads),
                &(cache.clone(), size, num_threads),
                |b, (cache, size, num_threads)| {
                    b.iter(|| {
                        let handles: Vec<_> = (0..*num_threads)
                            .map(|thread_id| {
                                let cache = Arc::clone(cache);
                                let tenant = tenant.to_string();
                                let size = *size;
                                thread::spawn(move || {
                                    for i in 0..1000 {
                                        let key = format!("origin-{}", (thread_id * 1000 + i) % size);
                                        let _ = cache.lookup(&key, &tenant);
                                    }
                                })
                            })
                            .collect();

                        for h in handles {
                            h.join().unwrap();
                        }
                    });
                },
            );
        }
    }

    group.finish();
}

criterion_group!(
    benches,
    bench_lookup_hit,
    bench_lookup_miss,
    bench_insert_small,
    bench_insert_large,
    bench_eviction,
    bench_concurrent_read,
);
criterion_main!(benches);
