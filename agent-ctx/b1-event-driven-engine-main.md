# Task: B1 Event-driven Actions Engine

## Summary
Implemented all 5 files for the B1 (Event-driven Actions Engine) component of the Zenic-Agents project. All files are production-quality Python 3.10+ with strict typing, retry logic, proper exports, and no bugs.

## Files Created

### 1. `src/core/events/__init__.py`
- Package init that re-exports all event-driven components
- 26 public symbols across 4 modules

### 2. `src/core/events/trigger_map.py`
- **TriggerMap**: Declarative mapping from event patterns to automations
- `register()` / `unregister()` / `lookup()` / `list_mappings()` methods
- Wildcard pattern matching via fnmatch (`db.*`, `sna.**` recursive)
- `TriggerCondition` with operators: eq, neq, gt, lt, contains, in
- Dot-notation field path resolution (e.g. `meta.severity`)
- Priority-based sorting (descending)
- `load_from_yaml()` and `load_from_dict()` bulk loading
- SQLite persistence (`trigger_map.sqlite`)
- Thread-safe with RLock
- Singleton pattern

### 3. `src/core/events/webhook_ingestion.py`
- **WebhookIngestionEngine**: Inbound webhook handler
- HMAC-SHA256 verification using `X-Hub-Signature-256` header
- Timing-safe comparison via `hmac.compare_digest`
- Signature length validation (max 256 chars) to prevent memory exhaustion
- JSON body parsing with error handling
- Schema validation via EventSchemaRegistry (non-fatal)
- Event dispatch via TriggerMap with retry (3 retries, exponential backoff: 1s, 2s, 4s)
- Endpoint registration, listing, and stats tracking
- SQLite persistence (`webhook_ingestion.sqlite`)
- Thread-safe with RLock
- Singleton pattern

### 4. `src/core/events/schema_registry.py`
- **EventSchemaRegistry**: In-memory event payload validation
- Schema format: `{required_fields, field_types, field_constraints}`
- Validation: missing fields, wrong types (with int→float coercion), constraint violations
- Constraints: min, max, min_length, max_length, pattern, allowed
- Permissive by default (no schema = valid)
- In-memory storage (no SQLite)
- Thread-safe with RLock
- Singleton pattern

### 5. `src/core/events/replay_queue.py`
- **ReplayQueue**: Dead-letter queue with event replay
- Status lifecycle: pending → retrying → succeeded / exhausted
- Exponential backoff: 1s, 2s, 4s between retries
- Max 3 retries before marking as exhausted
- `retry_event()`, `retry_batch()`, `replay_since()` methods
- `purge()` for cleaning old succeeded/exhausted events
- `get_stats()` with status counts and age metrics
- SQLite persistence (`replay_queue.sqlite`)
- Thread-safe with RLock
- Singleton pattern

## Test Results
All tests passed:
- EventSchemaRegistry: 7 checks ✓
- TriggerMap: 10 checks ✓
- WebhookIngestionEngine: 8 checks ✓
- ReplayQueue: 10 checks ✓

## Architecture Decisions
- SQLite for durable persistence (trigger_map, webhook_ingestion, replay_queue)
- In-memory for schema_registry (small data, can be re-loaded)
- Lazy dependency injection for cross-component references
- Each component can be instantiated independently with custom params
- All components use RLock for thread safety
- Singleton pattern via module-level `get_*()` / `reset_*()` functions
