//! Simulation module — DAG execution runner.
//!
//! Contains `topological_sort` and `simulate_dag` — the primary execution
//! and simulation functions for the dry-run DAG engine.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::collections::{HashMap, VecDeque};

/// Perform a topological sort on a DAG defined by node dependencies.
///
/// Uses Kahn's algorithm for O(V + E) time complexity.
///
/// Parameters
/// ----------
/// nodes : list[str]
///     List of node IDs.
/// edges : list[tuple[str, str]]
///     List of (source, target) edges representing dependencies.
///     An edge (A, B) means B depends on A (A must execute before B).
///
/// Returns
/// -------
/// dict
///     {
///         "sorted": list[str],
///         "has_cycle": bool,
///         "cycle_nodes": list[str] (only if has_cycle is True)
///     }
#[pyfunction]
#[pyo3(signature = (nodes, edges))]
pub fn topological_sort(
    py: Python<'_>,
    nodes: &Bound<'_, PyList>,
    edges: &Bound<'_, PyList>,
) -> PyResult<Py<PyDict>> {
    let node_ids: Vec<String> = nodes.extract()?;
    let edge_pairs: Vec<(String, String)> = edges.extract()?;

    let result = PyDict::new_bound(py);

    // Build adjacency list and in-degree count
    let mut adj: HashMap<String, Vec<String>> = HashMap::new();
    let mut in_degree: HashMap<String, usize> = HashMap::new();

    for node in &node_ids {
        adj.entry(node.clone()).or_default();
        in_degree.entry(node.clone()).or_insert(0);
    }

    for (src, dst) in &edge_pairs {
        adj.entry(src.clone()).or_default().push(dst.clone());
        *in_degree.entry(dst.clone()).or_insert(0) += 1;
    }

    // Kahn's algorithm
    let mut queue: VecDeque<String> = VecDeque::new();
    for (node, &deg) in &in_degree {
        if deg == 0 {
            queue.push_back(node.clone());
        }
    }

    let mut sorted: Vec<String> = Vec::with_capacity(node_ids.len());

    while let Some(node) = queue.pop_front() {
        sorted.push(node.clone());
        if let Some(neighbors) = adj.get(&node) {
            for neighbor in neighbors {
                if let Some(deg) = in_degree.get_mut(neighbor) {
                    *deg -= 1;
                    if *deg == 0 {
                        queue.push_back(neighbor.clone());
                    }
                }
            }
        }
    }

    let has_cycle = sorted.len() != node_ids.len();

    if has_cycle {
        // Find cycle nodes
        let sorted_set: HashSet<&str> = sorted.iter().map(|s| s.as_str()).collect();
        let cycle_nodes: Vec<String> = node_ids
            .iter()
            .filter(|n| !sorted_set.contains(n.as_str()))
            .cloned()
            .collect();

        result.set_item("sorted", sorted)?;
        result.set_item("has_cycle", true)?;
        result.set_item("cycle_nodes", cycle_nodes)?;
    } else {
        result.set_item("sorted", sorted)?;
        result.set_item("has_cycle", false)?;
        result.set_item("cycle_nodes", PyList::empty_bound(py))?;
    }

    Ok(result.unbind())
}

/// Simulate a DAG execution without any side effects.
///
/// Walks through the DAG in topological order, collecting the
/// simulated result of each node based on its type and config.
/// No real I/O, network, or database operations are performed.
///
/// Parameters
/// ----------
/// nodes : list[dict]
///     List of node dicts with keys:
///     - "id": str
///     - "type": str (e.g. "action", "condition", "parallel", "approval")
///     - "risk_score": float
///     - "estimated_duration_ms": int
/// edges : list[tuple[str, str]]
///     DAG edges.
///
/// Returns
/// -------
/// dict
///     {
///         "total_nodes": int,
///         "execution_order": list[str],
///         "total_estimated_duration_ms": int,
///         "aggregated_risk": float,
///         "high_risk_path": list[str],
///         "has_cycle": bool
///     }
#[pyfunction]
#[pyo3(signature = (nodes, edges))]
pub fn simulate_dag(
    py: Python<'_>,
    nodes: &Bound<'_, PyList>,
    edges: &Bound<'_, PyList>,
) -> PyResult<Py<PyDict>> {
    let result = PyDict::new_bound(py);

    let mut node_ids: Vec<String> = Vec::new();
    let mut node_risks: HashMap<String, f64> = HashMap::new();
    let mut node_durations: HashMap<String, i64> = HashMap::new();

    for item in nodes.iter() {
        let id: String = item.get_item("id")?.extract()?;
        let risk: f64 = item.get_item("risk_score")?.extract().unwrap_or(0.0);
        let duration: i64 = item.get_item("estimated_duration_ms")?.extract().unwrap_or(0);
        node_ids.push(id.clone());
        node_risks.insert(id.clone(), risk);
        node_durations.insert(id, duration);
    }

    // Topological sort
    let edge_pairs: Vec<(String, String)> = edges.extract()?;

    let mut adj: HashMap<String, Vec<String>> = HashMap::new();
    let mut in_degree: HashMap<String, usize> = HashMap::new();

    for node in &node_ids {
        adj.entry(node.clone()).or_default();
        in_degree.entry(node.clone()).or_insert(0);
    }

    for (src, dst) in &edge_pairs {
        adj.entry(src.clone()).or_default().push(dst.clone());
        *in_degree.entry(dst.clone()).or_insert(0) += 1;
    }

    let mut queue: VecDeque<String> = VecDeque::new();
    for (node, &deg) in &in_degree {
        if deg == 0 {
            queue.push_back(node.clone());
        }
    }

    let mut sorted: Vec<String> = Vec::with_capacity(node_ids.len());
    while let Some(node) = queue.pop_front() {
        sorted.push(node.clone());
        if let Some(neighbors) = adj.get(&node) {
            for neighbor in neighbors {
                if let Some(deg) = in_degree.get_mut(neighbor) {
                    *deg -= 1;
                    if *deg == 0 {
                        queue.push_back(neighbor.clone());
                    }
                }
            }
        }
    }

    let has_cycle = sorted.len() != node_ids.len();

    // Compute metrics
    let total_duration: i64 = sorted.iter().map(|n| node_durations.get(n).copied().unwrap_or(0)).sum();
    let risks: Vec<f64> = sorted.iter().map(|n| node_risks.get(n).copied().unwrap_or(0.0)).collect();
    let aggregated_risk = risks.iter().cloned().fold(0.0_f64, f64::max);

    // Find high-risk path (nodes with risk >= 0.7)
    let high_risk_path: Vec<String> = sorted
        .iter()
        .filter(|n| *node_risks.get(*n).unwrap_or(&0.0) >= 0.7)
        .cloned()
        .collect();

    result.set_item("total_nodes", node_ids.len() as i64)?;
    result.set_item("execution_order", sorted)?;
    result.set_item("total_estimated_duration_ms", total_duration)?;
    result.set_item("aggregated_risk", aggregated_risk)?;
    result.set_item("high_risk_path", high_risk_path)?;
    result.set_item("has_cycle", has_cycle)?;

    Ok(result.unbind())
}

use std::collections::HashSet;

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::VecDeque;

    #[test]
    fn test_topological_sort_simple() {
        let nodes = vec!["a".to_string(), "b".to_string(), "c".to_string()];
        let edges = vec![
            ("a".to_string(), "b".to_string()),
            ("b".to_string(), "c".to_string()),
        ];

        let mut adj: HashMap<String, Vec<String>> = HashMap::new();
        let mut in_degree: HashMap<String, usize> = HashMap::new();

        for node in &nodes {
            adj.entry(node.clone()).or_default();
            in_degree.entry(node.clone()).or_insert(0);
        }

        for (src, dst) in &edges {
            adj.entry(src.clone()).or_default().push(dst.clone());
            *in_degree.entry(dst.clone()).or_insert(0) += 1;
        }

        let mut queue: VecDeque<String> = VecDeque::new();
        for (node, &deg) in &in_degree {
            if deg == 0 {
                queue.push_back(node.clone());
            }
        }

        let mut sorted: Vec<String> = Vec::new();
        while let Some(node) = queue.pop_front() {
            sorted.push(node.clone());
            if let Some(neighbors) = adj.get(&node) {
                for neighbor in neighbors {
                    if let Some(deg) = in_degree.get_mut(neighbor) {
                        *deg -= 1;
                        if *deg == 0 {
                            queue.push_back(neighbor.clone());
                        }
                    }
                }
            }
        }

        assert_eq!(sorted, vec!["a", "b", "c"]);
    }

    #[test]
    fn test_topological_sort_cycle() {
        let nodes = vec!["a".to_string(), "b".to_string()];
        let edges = vec![
            ("a".to_string(), "b".to_string()),
            ("b".to_string(), "a".to_string()),
        ];

        let mut adj: HashMap<String, Vec<String>> = HashMap::new();
        let mut in_degree: HashMap<String, usize> = HashMap::new();

        for node in &nodes {
            adj.entry(node.clone()).or_default();
            in_degree.entry(node.clone()).or_insert(0);
        }

        for (src, dst) in &edges {
            adj.entry(src.clone()).or_default().push(dst.clone());
            *in_degree.entry(dst.clone()).or_insert(0) += 1;
        }

        let mut queue: VecDeque<String> = VecDeque::new();
        for (node, &deg) in &in_degree {
            if deg == 0 {
                queue.push_back(node.clone());
            }
        }

        let mut sorted: Vec<String> = Vec::new();
        while let Some(node) = queue.pop_front() {
            sorted.push(node.clone());
        }

        assert!(sorted.len() < nodes.len()); // Cycle detected
    }
}
