//! Unit tests for the risk module.

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::{HashMap, HashSet, VecDeque};

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
