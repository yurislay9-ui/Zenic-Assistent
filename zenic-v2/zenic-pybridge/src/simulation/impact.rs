//! Impact aggregation and DAG simulation functions.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::collections::{HashMap, VecDeque};

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
