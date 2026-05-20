//! Topological sort and cycle detection functions.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::collections::{HashMap, HashSet, VecDeque};

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
