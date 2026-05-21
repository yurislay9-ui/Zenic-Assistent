//! Benchmarks for `SemanticGraph` — the SQLite-backed deterministic knowledge graph.
//!
//! The `SemanticGraph` stores [`SemanticMapping`] records in a SQLite database
//! with WAL mode for concurrent reads.  These benchmarks measure the cost of
//! inserting and looking up mappings, plus concurrent lookup throughput,
//! parameterised across different dataset sizes.

use criterion::{
    black_box, criterion_group, criterion_main, BenchmarkId, Criterion, Throughput,
};
use std::sync::Arc;
use std::thread;

use zenic_memory::{LearningMechanism, SemanticGraph, SemanticMapping};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Creates a `SemanticMapping` for benchmarking.
fn make_mapping(id: usize, tenant: &str) -> SemanticMapping {
    SemanticMapping::new(
        format!("map-{id}"),
        format!("origin-{id}"),
        "synonym_of".to_string(),
        format!("dest-{id}"),
        LearningMechanism::SchemaDrift,
    )
    .with_tenant(tenant.to_string())
}

/// Pre-populates a graph with `count` mappings under a single tenant.
fn populate_graph(graph: &SemanticGraph, count: usize, tenant: &str) {
    for i in 0..count {
        let mapping = make_mapping(i, tenant);
        graph.insert_mapping(&mapping).unwrap();
    }
}

// We need a small extension to set the tenant_id on SemanticMapping.
trait SetTenant {
    fn with_tenant(self, tenant_id: String) -> Self;
}

impl SetTenant for SemanticMapping {
    fn with_tenant(mut self, tenant_id: String) -> Self {
        self.tenant_id = tenant_id;
        self
    }
}

// ---------------------------------------------------------------------------
// Benchmark: add_mapping
// ---------------------------------------------------------------------------

/// Measures the time to insert a single semantic mapping into the graph.
///
/// Each insert executes an SQL INSERT with 10 bound parameters plus WAL
/// journal flush.  This is the baseline write cost for the deterministic
/// knowledge graph.
fn bench_add_mapping(c: &mut Criterion) {
    let mut group = c.benchmark_group("semantic_graph/add_mapping");

    for &prepopulate in &[0usize, 100, 500, 2000] {
        group.throughput(Throughput::Elements(1));
        group.bench_with_input(
            BenchmarkId::new("existing_rows", prepopulate),
            &prepopulate,
            |b, &prepopulate| {
                let tenant = "tenant-insert";
                let mut idx = 0;
                b.iter(|| {
                    // Fresh in-memory DB each iteration for isolation
                    let graph = SemanticGraph::new(":memory:").unwrap();
                    populate_graph(&graph, prepopulate, tenant);

                    let mapping = make_mapping(prepopulate + idx, tenant);
                    graph.insert_mapping(black_box(&mapping)).unwrap();
                    idx += 1;
                });
            },
        );
    }

    group.finish();
}

// ---------------------------------------------------------------------------
// Benchmark: lookup_mapping
// ---------------------------------------------------------------------------

/// Measures the time to look up a mapping by origin + tenant_id.
///
/// Uses the `idx_origin_tenant` index, so this should be O(log n) in the
/// SQLite B-tree.  We parameterise by dataset size to verify index
/// scalability.
fn bench_lookup_mapping(c: &mut Criterion) {
    let mut group = c.benchmark_group("semantic_graph/lookup_mapping");

    for &count in &[100usize, 500, 2000, 5000] {
        let graph = SemanticGraph::new(":memory:").unwrap();
        let tenant = "tenant-lookup";
        populate_graph(&graph, count, tenant);

        group.throughput(Throughput::Elements(1));
        group.bench_with_input(
            BenchmarkId::new("dataset_size", count),
            &graph,
            |b, graph| {
                let mut idx = 0;
                b.iter(|| {
                    let origin = format!("origin-{}", idx % count);
                    let result = graph.lookup(black_box(&origin), black_box(tenant));
                    debug_assert!(result.is_ok());
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

/// Measures concurrent lookup throughput with multiple threads.
///
/// Each thread opens its own `rusqlite::Connection` to a shared in-memory
/// database (SQLite allows concurrent reads under WAL mode).  This benchmark
/// verifies that multi-reader access scales without lock contention.
fn bench_concurrent_lookups(c: &mut Criterion) {
    let mut group = c.benchmark_group("semantic_graph/concurrent_lookups");

    let count = 1000;
    let tenant = "tenant-concurrent";

    for &num_threads in &[1usize, 2, 4] {
        group.throughput(Throughput::Elements(num_threads as u64 * 500));
        group.bench_with_input(
            BenchmarkId::new("threads", num_threads),
            &num_threads,
            |b, &num_threads| {
                // We need a file-backed DB for multi-connection access;
                // in-memory DBs are connection-local in rusqlite.
                let tmp_dir = tempfile::tempdir().unwrap();
                let db_path = tmp_dir.path().join("bench.db");
                let db_path_str = db_path.to_str().unwrap();

                // Create and populate the shared DB
                {
                    let graph = SemanticGraph::new(db_path_str).unwrap();
                    populate_graph(&graph, count, tenant);
                }

                b.iter(|| {
                    let handles: Vec<_> = (0..num_threads)
                        .map(|thread_id| {
                            let db_path = db_path_str.to_string();
                            let tenant = tenant.to_string();
                            thread::spawn(move || {
                                let graph = SemanticGraph::new(&db_path).unwrap();
                                for i in 0..500 {
                                    let origin = format!("origin-{}", (thread_id * 500 + i) % count);
                                    let _ = graph.lookup(&origin, &tenant);
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

criterion_group!(benches, bench_add_mapping, bench_lookup_mapping, bench_concurrent_lookups);
criterion_main!(benches);
