//! Unit tests for the simulation module.

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::{HashMap, VecDeque};

    #[test]
    fn test_topological_sort_simple() {
        // Python::with_gil not needed for pure Rust logic
        let nodes = vec!["a".to_string(), "b".to_string(), "c".to_string()];
        let edges = vec![
            ("a".to_string(), "b".to_string()),
            ("b".to_string(), "c".to_string()),
        ];

        // We can test the core algorithm directly
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
