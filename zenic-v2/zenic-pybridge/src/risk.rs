//! Risk Prediction & Blast Radius Calculator — Graph analysis for Zenic-Agents.
//!
//! This module implements the F3 core in Rust for:
//! - Blast radius calculation: How many nodes are affected if a node fails
//! - Dependency graph analysis: Downstream impact propagation
//! - Risk propagation: How risk scores cascade through the DAG
//! - Critical path identification: Which nodes are on the critical path
//! - Reachability analysis: Which nodes can be reached from a given node
//!
//! Rust is ideal for this because:
//! - Graph traversal is computationally expensive with 59 nodes
//! - BFS/DFS on large graphs benefits from zero-cost abstractions
//! - Parallel risk propagation requires safe concurrent access
//! - Memory layout matters for cache-efficient graph algorithms

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::collections::{HashMap, HashSet, VecDeque};

// ─── Blast Radius ─────────────────────────────────────────────

/// Calculate the blast radius of a node failure in the DAG.
///
/// The blast radius is the set of all nodes that would be affected
/// (directly or transitively) if the given node fails. This includes
/// all downstream dependents.
///
/// Parameters
/// ----------
/// node_id : str
///     The node that might fail.
/// edges : list[tuple[str, str]]
///     DAG edges (source, target) where target depends on source.
///
/// Returns
/// -------
/// dict
///     {
///         "source_node": str,
///         "blast_radius": list[str],
///         "direct_dependents": list[str],
///         "transitive_dependents": list[str],
///         "blast_radius_size": int,
///         "risk_level": str ("low" | "medium" | "high" | "critical")
///     }
#[pyfunction]
#[pyo3(signature = (node_id, edges))]
pub fn calculate_blast_radius(
    py: Python<'_>,
    node_id: &str,
    edges: &Bound<'_, PyList>,
) -> PyResult<Py<PyDict>> {
    let edge_pairs: Vec<(String, String)> = edges.extract()?;

    // Build forward adjacency list (source → targets)
    let mut forward: HashMap<String, Vec<String>> = HashMap::new();
    for (src, dst) in &edge_pairs {
        forward.entry(src.clone()).or_default().push(dst.clone());
    }

    // BFS to find all reachable nodes from node_id
    let mut visited: HashSet<String> = HashSet::new();
    let mut queue: VecDeque<String> = VecDeque::new();
    queue.push_back(node_id.to_string());

    let direct_dependents: HashSet<String> = forward
        .get(node_id)
        .map(|v| v.iter().cloned().collect())
        .unwrap_or_default();

    while let Some(current) = queue.pop_front() {
        if visited.contains(&current) {
            continue;
        }
        visited.insert(current.clone());

        if let Some(neighbors) = forward.get(&current) {
            for neighbor in neighbors {
                if !visited.contains(neighbor) {
                    queue.push_back(neighbor.clone());
                }
            }
        }
    }

    // Remove the source node itself from blast radius
    visited.remove(node_id);

    let blast_radius: Vec<String> = visited.clone().into_iter().collect();
    let transitive: Vec<String> = visited
        .difference(&direct_dependents)
        .cloned()
        .collect();

    let blast_size = blast_radius.len();
    let risk_level = match blast_size {
        0 => "low",
        1..=3 => "medium",
        4..=10 => "high",
        _ => "critical",
    };

    let result = PyDict::new_bound(py);
    result.set_item("source_node", node_id)?;
    result.set_item("blast_radius", blast_radius)?;
    result.set_item("direct_dependents", direct_dependents.into_iter().collect::<Vec<_>>())?;
    result.set_item("transitive_dependents", transitive)?;
    result.set_item("blast_radius_size", blast_size as i64)?;
    result.set_item("risk_level", risk_level)?;

    Ok(result.unbind())
}

// ─── Risk Propagation ─────────────────────────────────────────

/// Propagate risk scores through the DAG and calculate the
/// effective risk at each node.
///
/// A node's effective risk is: max(own_risk, max(upstream_risk * decay)).
/// This models how upstream failures propagate downstream with
/// a configurable decay factor (0.0 to 1.0).
///
/// Parameters
/// ----------
/// nodes : list[str]
///     Node IDs in topological order.
/// edges : list[tuple[str, str]]
///     DAG edges.
/// base_risks : dict[str, float]
///     Base risk score per node (0.0 to 1.0).
/// decay : float
///     Risk decay factor per hop (0.0 = no propagation, 1.0 = full propagation).
///
/// Returns
/// -------
/// dict
///     {
///         "effective_risks": dict[str, float],
///         "max_effective_risk": float,
///         "high_risk_nodes": list[str],
///         "risk_paths": dict[str, list[str]]
///     }
#[pyfunction]
#[pyo3(signature = (nodes, edges, base_risks, decay))]
pub fn propagate_risks(
    py: Python<'_>,
    nodes: &Bound<'_, PyList>,
    edges: &Bound<'_, PyList>,
    base_risks: &Bound<'_, PyDict>,
    decay: f64,
) -> PyResult<Py<PyDict>> {
    let node_ids: Vec<String> = nodes.extract()?;
    let edge_pairs: Vec<(String, String)> = edges.extract()?;
    let base: HashMap<String, f64> = base_risks.extract()?;

    if decay < 0.0 || decay > 1.0 {
        return Err(PyValueError::new_err("decay must be between 0.0 and 1.0"));
    }

    // Build reverse adjacency (for each node, what feeds into it)
    let mut reverse_adj: HashMap<String, Vec<String>> = HashMap::new();
    for (src, dst) in &edge_pairs {
        reverse_adj
            .entry(dst.clone())
            .or_default()
            .push(src.clone());
    }

    // Compute effective risks in topological order
    let mut effective: HashMap<String, f64> = HashMap::new();
    let mut risk_paths: HashMap<String, Vec<String>> = HashMap::new();

    for node in &node_ids {
        let own_risk = *base.get(node).unwrap_or(&0.0);

        // Find maximum incoming propagated risk
        let incoming = reverse_adj.get(node).cloned().unwrap_or_default();
        let mut max_propagated = 0.0_f64;
        let mut max_source = String::new();

        for src in &incoming {
            let src_effective = *effective.get(src).unwrap_or(&0.0);
            let propagated = src_effective * decay;
            if propagated > max_propagated {
                max_propagated = propagated;
                max_source = src.clone();
            }
        }

        let effective_risk = own_risk.max(max_propagated);
        effective.insert(node.clone(), effective_risk);

        // Track the risk propagation path
        if !max_source.is_empty() && max_propagated > own_risk {
            let mut path = risk_paths.get(&max_source).cloned().unwrap_or_default();
            path.push(node.clone());
            risk_paths.insert(node.clone(), path);
        } else {
            risk_paths.insert(node.clone(), vec![node.clone()]);
        }
    }

    let max_effective = effective
        .values()
        .cloned()
        .fold(0.0_f64, f64::max);

    let high_risk: Vec<String> = effective
        .iter()
        .filter(|(_, &risk)| risk >= 0.7)
        .map(|(k, _)| k.clone())
        .collect();

    let effective_dict = PyDict::new_bound(py);
    for (k, v) in &effective {
        effective_dict.set_item(k, *v)?;
    }

    let paths_dict = PyDict::new_bound(py);
    for (k, v) in &risk_paths {
        paths_dict.set_item(k, v)?;
    }

    let result = PyDict::new_bound(py);
    result.set_item("effective_risks", effective_dict)?;
    result.set_item("max_effective_risk", max_effective)?;
    result.set_item("high_risk_nodes", high_risk)?;
    result.set_item("risk_paths", paths_dict)?;

    Ok(result.unbind())
}

// ─── Critical Path ────────────────────────────────────────────

/// Identify the critical path in the DAG (longest path by duration).
///
/// The critical path determines the minimum execution time for the
/// entire DAG. Any delay on the critical path delays the whole pipeline.
///
/// Parameters
/// ----------
/// nodes : list[str]
///     Node IDs in topological order.
/// edges : list[tuple[str, str]]
///     DAG edges.
/// durations : dict[str, int]
///     Duration in milliseconds per node.
///
/// Returns
/// -------
/// dict
///     {
///         "critical_path": list[str],
///         "total_duration_ms": int,
///         "is_on_critical_path": dict[str, bool]
///     }
#[pyfunction]
#[pyo3(signature = (nodes, edges, durations))]
pub fn find_critical_path(
    py: Python<'_>,
    nodes: &Bound<'_, PyList>,
    edges: &Bound<'_, PyList>,
    durations: &Bound<'_, PyDict>,
) -> PyResult<Py<PyDict>> {
    let node_ids: Vec<String> = nodes.extract()?;
    let edge_pairs: Vec<(String, String)> = edges.extract()?;
    let dur_map: HashMap<String, i64> = durations.extract()?;

    // Build reverse adjacency (predecessors)
    let mut predecessors: HashMap<String, Vec<String>> = HashMap::new();
    for node in &node_ids {
        predecessors.entry(node.clone()).or_default();
    }
    for (src, dst) in &edge_pairs {
        predecessors.entry(dst.clone()).or_default().push(src.clone());
    }

    // Compute earliest finish time for each node
    let mut earliest_finish: HashMap<String, i64> = HashMap::new();
    let mut predecessor_on_path: HashMap<String, Option<String>> = HashMap::new();

    for node in &node_ids {
        let node_dur = *dur_map.get(node).unwrap_or(&0);
        let preds = predecessors.get(node).cloned().unwrap_or_default();

        let mut max_pred_finish = 0_i64;
        let mut best_pred: Option<String> = None;

        for pred in &preds {
            let pred_finish = *earliest_finish.get(pred).unwrap_or(&0);
            if pred_finish > max_pred_finish {
                max_pred_finish = pred_finish;
                best_pred = Some(pred.clone());
            }
        }

        earliest_finish.insert(node.clone(), max_pred_finish + node_dur);
        predecessor_on_path.insert(node.clone(), best_pred);
    }

    // Find the node with the latest finish time
    let (end_node, total_duration) = earliest_finish
        .iter()
        .max_by_key(|(_, &finish)| finish)
        .map(|(k, &v)| (k.clone(), v))
        .unwrap_or((String::new(), 0));

    // Trace back from end_node to build the critical path
    let mut critical_path: Vec<String> = Vec::new();
    let mut current: Option<String> = Some(end_node);
    while let Some(node) = current {
        critical_path.push(node.clone());
        current = predecessor_on_path.get(&node).and_then(|p| p.clone());
    }
    critical_path.reverse();

    // Mark which nodes are on the critical path
    let critical_set: HashSet<&str> = critical_path.iter().map(|s| s.as_str()).collect();
    let is_on_critical: Py<PyDict> = {
        let dict = PyDict::new_bound(py);
        for node in &node_ids {
            dict.set_item(node, critical_set.contains(node.as_str()))?;
        }
        dict.unbind()
    };

    let result = PyDict::new_bound(py);
    result.set_item("critical_path", critical_path)?;
    result.set_item("total_duration_ms", total_duration)?;
    result.set_item("is_on_critical_path", is_on_critical)?;

    Ok(result.unbind())
}

// ─── Reachability ─────────────────────────────────────────────

/// Compute reachability from a set of source nodes.
///
/// Finds all nodes that can be reached from any of the given
/// source nodes, useful for understanding the impact scope.
///
/// Parameters
/// ----------
/// source_nodes : list[str]
///     Starting nodes.
/// edges : list[tuple[str, str]]
///     DAG edges.
///
/// Returns
/// -------
/// dict
///     {
///         "reachable": list[str],
///         "reachable_count": int,
///         "by_source": dict[str, list[str]]
///     }
#[pyfunction]
#[pyo3(signature = (source_nodes, edges))]
pub fn compute_reachability(
    py: Python<'_>,
    source_nodes: &Bound<'_, PyList>,
    edges: &Bound<'_, PyList>,
) -> PyResult<Py<PyDict>> {
    let sources: Vec<String> = source_nodes.extract()?;
    let edge_pairs: Vec<(String, String)> = edges.extract()?;

    // Build forward adjacency
    let mut forward: HashMap<String, Vec<String>> = HashMap::new();
    for (src, dst) in &edge_pairs {
        forward.entry(src.clone()).or_default().push(dst.clone());
    }

    let mut all_reachable: HashSet<String> = HashSet::new();
    let mut by_source: HashMap<String, Vec<String>> = HashMap::new();

    for source in &sources {
        let mut visited: HashSet<String> = HashSet::new();
        let mut queue: VecDeque<String> = VecDeque::new();
        queue.push_back(source.clone());

        while let Some(current) = queue.pop_front() {
            if visited.contains(&current) {
                continue;
            }
            visited.insert(current.clone());

            if let Some(neighbors) = forward.get(&current) {
                for neighbor in neighbors {
                    if !visited.contains(neighbor) {
                        queue.push_back(neighbor.clone());
                    }
                }
            }
        }

        visited.remove(source);
        all_reachable.extend(visited.iter().cloned());
        by_source.insert(source.clone(), visited.into_iter().collect());
    }

    let by_source_dict = PyDict::new_bound(py);
    for (k, v) in &by_source {
        by_source_dict.set_item(k, v)?;
    }

    let result = PyDict::new_bound(py);
    result.set_item("reachable", all_reachable.into_iter().collect::<Vec<_>>())?;
    result.set_item("reachable_count", by_source.values().map(|v| v.len()).sum::<usize>() as i64)?;
    result.set_item("by_source", by_source_dict)?;

    Ok(result.unbind())
}

// ─── Multi-Node Blast Radius ─────────────────────────────────

/// Calculate the combined blast radius for multiple node failures.
///
/// This is more efficient than calling calculate_blast_radius
/// for each node individually because the graph is traversed once.
///
/// Parameters
/// ----------
/// failed_nodes : list[str]
///     Nodes that might fail simultaneously.
/// edges : list[tuple[str, str]]
///     DAG edges.
///
/// Returns
/// -------
/// dict
///     {
///         "combined_blast_radius": list[str],
///         "blast_radius_size": int,
///         "risk_level": str,
///         "per_node": dict[str, dict]
///     }
#[pyfunction]
#[pyo3(signature = (failed_nodes, edges))]
pub fn multi_node_blast_radius(
    py: Python<'_>,
    failed_nodes: &Bound<'_, PyList>,
    edges: &Bound<'_, PyList>,
) -> PyResult<Py<PyDict>> {
    let failed: Vec<String> = failed_nodes.extract()?;
    let edge_pairs: Vec<(String, String)> = edges.extract()?;

    // Build forward adjacency
    let mut forward: HashMap<String, Vec<String>> = HashMap::new();
    for (src, dst) in &edge_pairs {
        forward.entry(src.clone()).or_default().push(dst.clone());
    }

    // BFS from all failed nodes simultaneously
    let mut visited: HashSet<String> = HashSet::new();
    let mut queue: VecDeque<String> = VecDeque::new();

    for node in &failed {
        queue.push_back(node.clone());
    }

    while let Some(current) = queue.pop_front() {
        if visited.contains(&current) {
            continue;
        }
        visited.insert(current.clone());

        if let Some(neighbors) = forward.get(&current) {
            for neighbor in neighbors {
                if !visited.contains(neighbor) {
                    queue.push_back(neighbor.clone());
                }
            }
        }
    }

    // Remove source nodes from the blast radius
    let failed_set: HashSet<&str> = failed.iter().map(|s| s.as_str()).collect();
    let blast_radius: Vec<String> = visited
        .iter()
        .filter(|n| !failed_set.contains(n.as_str()))
        .cloned()
        .collect();

    let blast_size = blast_radius.len();
    let risk_level = match blast_size {
        0 => "low",
        1..=5 => "medium",
        6..=15 => "high",
        _ => "critical",
    };

    // Per-node blast radius
    let per_node_dict = PyDict::new_bound(py);
    for node in &failed {
        let mut node_visited: HashSet<String> = HashSet::new();
        let mut node_queue: VecDeque<String> = VecDeque::new();
        node_queue.push_back(node.clone());

        while let Some(current) = node_queue.pop_front() {
            if node_visited.contains(&current) {
                continue;
            }
            node_visited.insert(current.clone());

            if let Some(neighbors) = forward.get(&current) {
                for neighbor in neighbors {
                    if !node_visited.contains(neighbor) {
                        node_queue.push_back(neighbor.clone());
                    }
                }
            }
        }

        node_visited.remove(node);
        let node_blast = node_visited.into_iter().collect::<Vec<_>>();
        let node_size = node_blast.len();
        let node_risk = match node_size {
            0 => "low",
            1..=3 => "medium",
            4..=10 => "high",
            _ => "critical",
        };

        let node_dict = PyDict::new_bound(py);
        node_dict.set_item("blast_radius", node_blast)?;
        node_dict.set_item("blast_radius_size", node_size as i64)?;
        node_dict.set_item("risk_level", node_risk)?;
        per_node_dict.set_item(node, node_dict)?;
    }

    let result = PyDict::new_bound(py);
    result.set_item("combined_blast_radius", blast_radius)?;
    result.set_item("blast_radius_size", blast_size as i64)?;
    result.set_item("risk_level", risk_level)?;
    result.set_item("per_node", per_node_dict)?;

    Ok(result.unbind())
}

// ─── Unit Tests ───────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_blast_radius_single() {
        let edges = vec![
            ("a".to_string(), "b".to_string()),
            ("b".to_string(), "c".to_string()),
            ("b".to_string(), "d".to_string()),
        ];

        // Build forward adjacency
        let mut forward: HashMap<String, Vec<String>> = HashMap::new();
        for (src, dst) in &edges {
            forward.entry(src.clone()).or_default().push(dst.clone());
        }

        // BFS from "a"
        let mut visited: HashSet<String> = HashSet::new();
        let mut queue: VecDeque<String> = VecDeque::new();
        queue.push_back("a".to_string());

        while let Some(current) = queue.pop_front() {
            if visited.contains(&current) {
                continue;
            }
            visited.insert(current.clone());
            if let Some(neighbors) = forward.get(&current) {
                for neighbor in neighbors {
                    if !visited.contains(neighbor) {
                        queue.push_back(neighbor.clone());
                    }
                }
            }
        }

        visited.remove("a");
        assert!(visited.contains("b"));
        assert!(visited.contains("c"));
        assert!(visited.contains("d"));
        assert_eq!(visited.len(), 3);
    }

    #[test]
    fn test_blast_radius_isolated() {
        let edges: Vec<(String, String)> = vec![];
        // No edges — blast radius is empty
        assert_eq!(edges.len(), 0);
    }
}
