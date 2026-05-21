//! Benchmarks for `OntologyBase` — the shared ontology layer.
//!
//! The `OntologyBase` holds ~50 built-in Spanish business term mappings in a
//! `Vec<SemanticMapping>` and supports per-tenant overrides via a
//! `RwLock<HashMap<String, Vec<SemanticMapping>>>`.  Lookups perform a linear
//! scan of the tenant overrides followed by a linear scan of the base
//! mappings.  These benchmarks measure the cost of exact match, prefix scan,
//! and miss scenarios, plus the overhead of tenant override resolution.

use criterion::{
    black_box, criterion_group, criterion_main, BenchmarkId, Criterion, Throughput,
};
use std::sync::Arc;
use std::thread;

use zenic_memory::{LearningMechanism, OntologyBase, SemanticMapping};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Creates a `SemanticMapping` suitable for tenant overrides.
fn make_override_mapping(id: usize) -> SemanticMapping {
    SemanticMapping::new(
        format!("override-{id}"),
        format!("term-{id}"),
        "synonym_of".to_string(),
        format!("override-dest-{id}"),
        LearningMechanism::IntentRouting,
    )
}

/// Adds `count` tenant overrides for a given tenant.
fn add_overrides(ontology: &OntologyBase, count: usize, tenant: &str) {
    for i in 0..count {
        let mapping = make_override_mapping(i);
        ontology.add_tenant_override(tenant, mapping).unwrap();
    }
}

// ---------------------------------------------------------------------------
// Benchmark: search_exact (base mapping)
// ---------------------------------------------------------------------------

/// Measures the time to look up an existing term in the base mappings.
///
/// The base mappings are stored as a `Vec<SemanticMapping>`, so lookups are
/// O(n) linear scans.  With ~50 built-in terms this is fast, but it's
/// important to verify the cost stays low as the ontology grows.
fn bench_search_exact(c: &mut Criterion) {
    let mut group = c.benchmark_group("ontology_base/search_exact");

    let ontology = OntologyBase::new().unwrap();
    let base_count = ontology.base_count();

    // Use the first known built-in term: "cobro" (from ont-fin-001)
    let known_terms: Vec<&str> = vec!["cobro", "pago", "cuenta", "saldo", "factura"];

    group.throughput(Throughput::Elements(1));
    group.bench_function(
        BenchmarkId::new("base_mappings", base_count),
        |b| {
            let mut idx = 0;
            b.iter(|| {
                let term = known_terms[idx % known_terms.len()];
                let result = ontology.lookup(black_box(term), black_box("__anonymous__"));
                debug_assert!(result.is_some());
                idx += 1;
            });
        },
    );

    // Also benchmark with varying numbers of tenant overrides to measure
    // the cost of the override check before the base fallback.
    for &override_count in &[0usize, 10, 50, 200] {
        let tenant = "tenant-exact";
        let ont = OntologyBase::new().unwrap();
        add_overrides(&ont, override_count, tenant);

        group.throughput(Throughput::Elements(1));
        group.bench_with_input(
            BenchmarkId::new("with_overrides", override_count),
            &ont,
            |b, ont| {
                let mut idx = 0;
                b.iter(|| {
                    let term = known_terms[idx % known_terms.len()];
                    // Lookup a base term under the override tenant
                    // (no override match, falls through to base)
                    let result = ont.lookup(black_box(term), black_box(tenant));
                    debug_assert!(result.is_some());
                    idx += 1;
                });
            },
        );
    }

    group.finish();
}

// ---------------------------------------------------------------------------
// Benchmark: search_prefix
// ---------------------------------------------------------------------------

/// Measures the cost of a prefix-style scan across the ontology.
///
/// The `OntologyBase` does not natively support prefix queries — a prefix
/// search requires iterating `all_mappings()` and filtering.  This benchmark
/// models that pattern: scan all base mappings and collect those whose
/// `origin` starts with a given prefix.
///
/// Useful for understanding the throughput of bulk ontology traversal.
fn bench_search_prefix(c: &mut Criterion) {
    let mut group = c.benchmark_group("ontology_base/search_prefix");

    let ontology = OntologyBase::new().unwrap();
    let base_count = ontology.base_count();

    // Prefixes that match varying fractions of the built-in terms
    let prefixes: Vec<&str> = vec!["cob", "po", "c", "on"];

    group.throughput(Throughput::Elements(base_count as u64));
    group.bench_function(
        BenchmarkId::new("base_mappings", base_count),
        |b| {
            let mut idx = 0;
            b.iter(|| {
                let prefix = prefixes[idx % prefixes.len()];
                let _matches: Vec<_> = ontology
                    .all_mappings()
                    .iter()
                    .filter(|m| m.origin.starts_with(prefix))
                    .collect();
                idx += 1;
            });
        },
    );

    group.finish();
}

// ---------------------------------------------------------------------------
// Benchmark: search_miss
// ---------------------------------------------------------------------------

/// Measures the time to look up a non-existing term in the ontology.
///
/// A miss scans all tenant overrides (if any) and all base mappings without
/// finding a match — this is the worst-case path length.  Important to
/// benchmark because misses are common in production when new terms arrive.
fn bench_search_miss(c: &mut Criterion) {
    let mut group = c.benchmark_group("ontology_base/search_miss");

    // Test miss cost with varying numbers of tenant overrides.
    // More overrides → longer scan of the tenant override Vec.
    for &override_count in &[0usize, 10, 50, 200, 500] {
        let tenant = "tenant-miss";
        let ontology = OntologyBase::new().unwrap();
        add_overrides(&ontology, override_count, tenant);

        group.throughput(Throughput::Elements(1));
        group.bench_with_input(
            BenchmarkId::new("override_count", override_count),
            &ontology,
            |b, ontology| {
                let mut idx = 0;
                b.iter(|| {
                    // Term that doesn't exist in either base or overrides
                    let term = format!("nonexistent-term-{idx}");
                    let result = ontology.lookup(black_box(&term), black_box(tenant));
                    debug_assert!(result.is_none());
                    idx += 1;
                });
            },
        );
    }

    group.finish();
}

// ---------------------------------------------------------------------------
// Benchmark: add_tenant_override
// ---------------------------------------------------------------------------

/// Measures the cost of adding a tenant override.
///
/// This requires acquiring a write lock on the `tenant_overrides` map and
/// pushing to the tenant's `Vec<SemanticMapping>`.  Parameterised by the
/// number of existing overrides for the tenant to measure Vec push cost
/// growth.
fn bench_add_tenant_override(c: &mut Criterion) {
    let mut group = c.benchmark_group("ontology_base/add_tenant_override");

    for &existing_overrides in &[0usize, 10, 50, 200] {
        group.throughput(Throughput::Elements(1));
        group.bench_with_input(
            BenchmarkId::new("existing_overrides", existing_overrides),
            &existing_overrides,
            |b, &existing_overrides| {
                let tenant = "tenant-add";
                let mut idx = 0;
                b.iter(|| {
                    let ontology = OntologyBase::new().unwrap();
                    add_overrides(&ontology, existing_overrides, tenant);

                    let mapping = make_override_mapping(existing_overrides + idx);
                    ontology
                        .add_tenant_override(black_box(tenant), black_box(mapping))
                        .unwrap();
                    idx += 1;
                });
            },
        );
    }

    group.finish();
}

// ---------------------------------------------------------------------------
// Benchmark: concurrent_lookups
// ---------------------------------------------------------------------------

/// Measures concurrent lookup throughput on the ontology base.
///
/// The `RwLock` on `tenant_overrides` allows concurrent reads.  This
/// benchmark verifies that multi-threaded read access to the ontology
/// scales without contention.
fn bench_concurrent_lookups(c: &mut Criterion) {
    let mut group = c.benchmark_group("ontology_base/concurrent_lookups");

    let ontology = Arc::new(OntologyBase::new().unwrap());
    let base_count = ontology.base_count();
    let known_terms: Vec<&str> = vec!["cobro", "pago", "cuenta", "saldo", "factura"];

    for &num_threads in &[1usize, 2, 4] {
        group.throughput(Throughput::Elements(num_threads as u64 * 1000));
        group.bench_with_input(
            BenchmarkId::new("threads", num_threads),
            &num_threads,
            |b, &num_threads| {
                b.iter(|| {
                    let handles: Vec<_> = (0..num_threads)
                        .map(|thread_id| {
                            let ontology = Arc::clone(&ontology);
                            let tenant = format!("tenant-{}", thread_id);
                            thread::spawn(move || {
                                for i in 0..1000 {
                                    let term = known_terms[(thread_id * 1000 + i) % known_terms.len()];
                                    let _ = ontology.lookup(term, &tenant);
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

    group.finish();
}

criterion_group!(
    benches,
    bench_search_exact,
    bench_search_prefix,
    bench_search_miss,
    bench_add_tenant_override,
    bench_concurrent_lookups,
);
criterion_main!(benches);
