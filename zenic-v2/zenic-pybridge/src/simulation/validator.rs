//! Simulation module — DAG validation and impact aggregation.
//!
//! Contains `detect_cycles` and `aggregate_impact` — the analysis
//! and validation functions for the dry-run DAG engine.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::collections::HashMap;

/// Detect cycles in a directed graph using DFS.
///
/// More efficient than topological_sort when you only need to know
/// if a cycle exists, not the full ordering.
///
/// Parameters
/// ----------
/// nodes : list[str]
/// edges : list[tuple[str, str]]
///
/// Returns
/// -------
/// dict
///     {
///         "has_cycle": bool,
///         "cycle_path": list[str] (one cycle if found, empty otherwise)
///     }
#[pyfunction]
#[pyo3(signature = (nodes, edges))]
pub fn detect_cycles(
    py: Python<'_>,
    nodes: &Bound<'_, PyList>,
    edges: &Bound<'_, PyList>,
) -> PyResult<Py<PyDict>> {
    let node_ids: Vec<String> = nodes.extract()?;
    let edge_pairs: Vec<(String, String)> = edges.extract()?;

    let result = PyDict::new_bound(py);

    // Build adjacency list
    let mut adj: HashMap<String, Vec<String>> = HashMap::new();
    for node in &node_ids {
        adj.entry(node.clone()).or_default();
    }
    for (src, dst) in &edge_pairs {
        adj.entry(src.clone()).or_default().push(dst.clone());
    }

    // DFS with color marking: 0=white (unvisited), 1=gray (in progress), 2=black (done)
    let mut color: HashMap<String, u8> = HashMap::new();
    let mut parent: HashMap<String, Option<String>> = HashMap::new();
    for node in &node_ids {
        color.insert(node.clone(), 0);
        parent.insert(node.clone(), None);
    }

    let mut cycle_path: Vec<String> = Vec::new();

    fn dfs(
        node: &str,
        adj: &HashMap<String, Vec<String>>,
        color: &mut HashMap<String, u8>,
        parent: &mut HashMap<String, Option<String>>,
        cycle_path: &mut Vec<String>,
    ) -> bool {
        color.insert(node.to_string(), 1); // Gray

        if let Some(neighbors) = adj.get(node) {
            for neighbor in neighbors {
                let neighbor_color = *color.get(neighbor).unwrap_or(&0);
                if neighbor_color == 1 {
                    // Found a cycle — reconstruct path
                    cycle_path.clear();
                    cycle_path.push(neighbor.clone());
                    let mut current = Some(node.to_string());
                    while let Some(curr) = current {
                        cycle_path.push(curr.clone());
                        if curr == *neighbor {
                            break;
                        }
                        current = parent.get(&curr).and_then(|p| p.clone());
                    }
                    cycle_path.reverse();
                    return true;
                }
                if neighbor_color == 0 {
                    parent.insert(neighbor.clone(), Some(node.to_string()));
                    if dfs(neighbor, adj, color, parent, cycle_path) {
                        return true;
                    }
                }
            }
        }

        color.insert(node.to_string(), 2); // Black
        false
    }

    let mut found_cycle = false;
    for node in &node_ids {
        if *color.get(node).unwrap_or(&0) == 0 {
            if dfs(node, &adj, &mut color, &mut parent, &mut cycle_path) {
                found_cycle = true;
                break;
            }
        }
    }

    result.set_item("has_cycle", found_cycle)?;
    result.set_item("cycle_path", &cycle_path)?;

    Ok(result.unbind())
}

/// Aggregate risk scores across a DAG execution path.
///
/// Traverses the DAG in topological order, combining risk scores
/// using a configurable strategy:
///   - "max": Take the maximum risk score (any single node failure = total failure)
///   - "sum": Sum all risk scores (cumulative risk)
///   - "avg": Average risk scores (mean risk)
///   - "weighted_avg": Weight by node depth (deeper = more impactful)
///
/// Parameters
/// ----------
/// sorted_nodes : list[str]
///     Nodes in topological order.
/// edges : list[tuple[str, str]]
///     DAG edges.
/// risk_scores : dict[str, float]
///     Mapping of node_id → risk_score (0.0 to 1.0).
/// strategy : str
///     Aggregation strategy: "max", "sum", "avg", "weighted_avg".
///
/// Returns
/// -------
/// dict
///     {
///         "aggregated_score": float,
///         "strategy": str,
///         "node_count": int,
///         "max_score": float,
///         "min_score": float,
///         "high_risk_nodes": list[str] (nodes with score >= 0.7)
///     }
#[pyfunction]
#[pyo3(signature = (sorted_nodes, _edges, risk_scores, strategy))]
pub fn aggregate_impact(
    py: Python<'_>,
    sorted_nodes: &Bound<'_, PyList>,
    _edges: &Bound<'_, PyList>,
    risk_scores: &Bound<'_, PyDict>,
    strategy: &str,
) -> PyResult<Py<PyDict>> {
    let nodes: Vec<String> = sorted_nodes.extract()?;
    let risk_map: HashMap<String, f64> = risk_scores.extract()?;

    if nodes.is_empty() {
        let result = PyDict::new_bound(py);
        result.set_item("aggregated_score", 0.0)?;
        result.set_item("strategy", strategy)?;
        result.set_item("node_count", 0)?;
        result.set_item("max_score", 0.0)?;
        result.set_item("min_score", 0.0)?;
        result.set_item("high_risk_nodes", PyList::empty_bound(py))?;
        return Ok(result.unbind());
    }

    let mut scores: Vec<f64> = Vec::with_capacity(nodes.len());
    let mut high_risk_nodes: Vec<String> = Vec::new();

    for (_depth, node) in nodes.iter().enumerate() {
        let score = *risk_map.get(node).unwrap_or(&0.0);
        scores.push(score);
        if score >= 0.7 {
            high_risk_nodes.push(node.clone());
        }
    }

    let aggregated = match strategy {
        "max" => scores.iter().cloned().fold(0.0_f64, f64::max),
        "sum" => scores.iter().sum(),
        "avg" => scores.iter().sum::<f64>() / scores.len() as f64,
        "weighted_avg" => {
            let total_weight: f64 = (1..=nodes.len()).map(|i| i as f64).sum();
            scores
                .iter()
                .enumerate()
                .map(|(i, &s)| s * ((i + 1) as f64))
                .sum::<f64>()
                / total_weight
        }
        _ => {
            return Err(PyValueError::new_err(format!(
                "Unknown strategy '{}'. Use: max, sum, avg, weighted_avg",
                strategy
            )));
        }
    };

    let max_score = scores.iter().cloned().fold(0.0_f64, f64::max);
    let min_score = scores.iter().cloned().fold(1.0_f64, f64::min);

    let result = PyDict::new_bound(py);
    result.set_item("aggregated_score", aggregated)?;
    result.set_item("strategy", strategy)?;
    result.set_item("node_count", nodes.len() as i64)?;
    result.set_item("max_score", max_score)?;
    result.set_item("min_score", min_score)?;
    result.set_item("high_risk_nodes", high_risk_nodes)?;

    Ok(result.unbind())
}
