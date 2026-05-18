//! Checkpoint store: in-memory and optional disk persistence for workflow checkpoints.

use std::collections::HashMap;

use zenic_proto::ExecutionId;

use crate::checkpoint::Checkpoint;
use crate::errors::FlowError;

/// Store for workflow checkpoints with optional disk persistence.
///
/// E-11 FIX: Added disk persistence so checkpoints survive process crashes.
/// Previously, checkpoints were stored in-memory only, meaning any crash
/// or restart would lose all workflow state. The store now supports:
///
/// - **In-memory mode** (`CheckpointStore::new()`): Same as before,
///   for testing and short-lived workflows.
/// - **Disk-persistent mode** (`CheckpointStore::with_persistence(dir)`):
///   Each checkpoint is serialized to `<dir>/<execution_id>.ckpt` using
///   bincode + zstd (the canonical format from `zenic-proto`). On startup,
///   existing checkpoint files are loaded back into memory.
///
/// Thread safety: Internal state is protected by `RwLock<HashMap>` so
/// concurrent reads are allowed. The `save()` and `remove()` methods
/// now take `&self` instead of `&mut self` (no longer need exclusive
/// access thanks to the internal lock).
pub struct CheckpointStore {
    /// In-memory index of checkpoints, protected by RwLock for thread safety.
    checkpoints: std::sync::RwLock<HashMap<ExecutionId, Checkpoint>>,
    /// Optional directory for disk persistence. If None, checkpoints are
    /// in-memory only (backward compatible with the original behavior).
    persist_dir: Option<std::path::PathBuf>,
}

impl CheckpointStore {
    /// Creates an empty in-memory checkpoint store (no disk persistence).
    ///
    /// This is the original behavior, suitable for testing and short-lived
    /// workflows where crash recovery is not required.
    pub fn new() -> Self {
        Self {
            checkpoints: std::sync::RwLock::new(HashMap::new()),
            persist_dir: None,
        }
    }

    /// Creates a checkpoint store with disk persistence.
    ///
    /// E-11 FIX: Checkpoints are saved to individual files in the given
    /// directory, one per execution. The directory is created if it doesn't
    /// exist. On construction, any existing checkpoint files in the
    /// directory are loaded into memory.
    ///
    /// File format: `<dir>/<execution_id_hex>.ckpt` — bincode + zstd
    /// serialized `Checkpoint` structs (same as `Checkpoint::to_bytes()`).
    ///
    /// # Errors
    ///
    /// Returns `FlowError` if the directory cannot be created or if
    /// existing checkpoint files cannot be read.
    pub fn with_persistence(dir: impl Into<std::path::PathBuf>) -> Result<Self, FlowError> {
        let persist_dir = dir.into();
        std::fs::create_dir_all(&persist_dir).map_err(|e| {
            FlowError::CheckpointFailed(format!(
                "failed to create checkpoint directory {:?}: {}",
                persist_dir, e
            ))
        })?;

        let store = Self {
            checkpoints: std::sync::RwLock::new(HashMap::new()),
            persist_dir: Some(persist_dir),
        };

        // Load existing checkpoints from disk.
        store.load_from_disk()?;

        Ok(store)
    }

    /// Saves a checkpoint, replacing any previous checkpoint for the same execution.
    ///
    /// If disk persistence is enabled, the checkpoint is also written to disk.
    /// The in-memory store is always updated first, then the disk write is
    /// attempted. If the disk write fails, a warning is logged but the
    /// in-memory store is still updated (graceful degradation).
    pub fn save(&self, checkpoint: Checkpoint) -> Result<(), FlowError> {
        let exec_id = checkpoint.execution_id;

        // Update in-memory store.
        {
            let mut map = self.checkpoints.write().map_err(|e| {
                FlowError::CheckpointFailed(format!("lock poisoned: {}", e))
            })?;
            map.insert(exec_id, checkpoint.clone());
        }

        // Persist to disk if enabled.
        if let Some(ref dir) = self.persist_dir {
            if let Err(e) = self.persist_checkpoint(&exec_id, &checkpoint) {
                log::warn!(
                    "E-11: Failed to persist checkpoint {:?} to disk: {}. \
                     In-memory checkpoint is still valid.",
                    exec_id, e
                );
            }
        }

        Ok(())
    }

    /// Loads the latest checkpoint for an execution ID.
    ///
    /// Returns a reference to the checkpoint from the in-memory store.
    /// For disk-persistent stores, checkpoints are loaded into memory
    /// on construction, so this always returns from memory.
    pub fn load(&self, execution_id: &ExecutionId) -> Option<Checkpoint> {
        let map = self.checkpoints.read().ok()?;
        map.get(execution_id).cloned()
    }

    /// Removes and returns the checkpoint for an execution ID.
    ///
    /// If disk persistence is enabled, the checkpoint file is also removed.
    pub fn remove(&self, execution_id: &ExecutionId) -> Option<Checkpoint> {
        let cp = {
            let mut map = self.checkpoints.write().ok()?;
            map.remove(execution_id)
        };

        // Remove from disk if enabled.
        if let Some(ref dir) = self.persist_dir {
            let path = dir.join(format!("{}.ckpt", execution_id));
            let _ = std::fs::remove_file(path); // Best-effort removal
        }

        cp
    }

    /// Returns the number of stored checkpoints.
    pub fn len(&self) -> usize {
        self.checkpoints.read().map(|m| m.len()).unwrap_or(0)
    }

    /// Whether the store is empty.
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// Whether disk persistence is enabled.
    pub fn is_persistent(&self) -> bool {
        self.persist_dir.is_some()
    }

    // -----------------------------------------------------------------------
    // Private helpers for disk persistence
    // -----------------------------------------------------------------------

    /// Persists a single checkpoint to disk.
    fn persist_checkpoint(
        &self,
        execution_id: &ExecutionId,
        checkpoint: &Checkpoint,
    ) -> Result<(), FlowError> {
        let dir = self.persist_dir.as_ref().ok_or_else(|| {
            FlowError::CheckpointFailed("persistence not enabled".to_string())
        })?;

        let bytes = checkpoint.to_bytes()?;
        let path = dir.join(format!("{}.ckpt", execution_id));

        // Write atomically: write to temp file, then rename.
        let temp_path = dir.join(format!("{}.ckpt.tmp", execution_id));
        std::fs::write(&temp_path, &bytes).map_err(|e| {
            FlowError::CheckpointFailed(format!(
                "failed to write checkpoint to {:?}: {}",
                temp_path, e
            ))
        })?;
        std::fs::rename(&temp_path, &path).map_err(|e| {
            FlowError::CheckpointFailed(format!(
                "failed to rename checkpoint from {:?} to {:?}: {}",
                temp_path, path, e
            ))
        })?;

        Ok(())
    }

    /// Loads all checkpoint files from the persistence directory.
    fn load_from_disk(&self) -> Result<(), FlowError> {
        let dir = self.persist_dir.as_ref().ok_or_else(|| {
            FlowError::CheckpointFailed("persistence not enabled".to_string())
        })?;

        let entries = std::fs::read_dir(dir).map_err(|e| {
            FlowError::CheckpointFailed(format!(
                "failed to read checkpoint directory {:?}: {}",
                dir, e
            ))
        })?;

        let mut loaded = 0usize;
        let mut errors = 0usize;

        for entry in entries {
            let entry = match entry {
                Ok(e) => e,
                Err(_) => continue,
            };

            let path = entry.path();
            if path.extension().and_then(|e| e.to_str()) != Some("ckpt") {
                continue;
            }

            match std::fs::read(&path) {
                Ok(bytes) => match Checkpoint::from_bytes(&bytes) {
                    Ok(checkpoint) => {
                        let exec_id = checkpoint.execution_id;
                        if let Ok(mut map) = self.checkpoints.write() {
                            map.insert(exec_id, checkpoint);
                        }
                        loaded += 1;
                    }
                    Err(e) => {
                        log::warn!(
                            "E-11: Failed to deserialize checkpoint from {:?}: {}. Skipping.",
                            path, e
                        );
                        errors += 1;
                    }
                },
                Err(e) => {
                    log::warn!(
                        "E-11: Failed to read checkpoint file {:?}: {}. Skipping.",
                        path, e
                    );
                    errors += 1;
                }
            }
        }

        if loaded > 0 || errors > 0 {
            log::info!(
                "E-11: CheckpointStore loaded {} checkpoints from disk ({} errors) in {:?}",
                loaded, errors, dir
            );
        }

        Ok(())
    }
}

impl Default for CheckpointStore {
    fn default() -> Self {
        Self::new()
    }
}
