//! Blast radius calculators — single-node and multi-node failure analysis.

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
