# 🏗️ Plan Maestro de Modularización — Zenic-Agents v3.0.0

> **Objetivo**: Ningún archivo debe superar las **400 líneas**.  
> Cada archivo que exceda el límite se divide en sub-carpetas con módulos acotados.

---

## 📐 Límites por Stack Tecnológico

| Lenguaje | Rango Ideal (Media) | Límite Máximo | Estrategia de Splitting |
|----------|--------------------|---------------|------------------------|
| **Rust (zenic-v2/)** | 100-250 líneas | 500 líneas | Dividir en `mod` separados; `mod.rs` solo re-exports |
| **Python (src/core/)** | 150-300 líneas | 600 líneas | Mixins, composición, sub-módulos con `__init__.py` que re-exporta |
| **TypeScript (gateway/)** | 100-200 líneas | 400 líneas | Separar `types/`, `services/`, `utils/` de componentes y rutas API |

---

## 📊 Estado Actual — 194 Archivos con 400+ Líneas

| Módulo | 1000+ | 800-999 | 600-799 | 400-599 | Total líneas exceso |
|--------|-------|---------|---------|---------|-------------------|
| **src/core (Python)** | 6 | 9 | 24 | 45 | 54,517 |
| **gateway (TS/TSX)** | 15 | 8 | 5 | 12 | 63,478 |
| **zenic-v2 (Rust)** | 10 | 6 | 5 | 16 | 30,873 |
| **TOTAL** | **31** | **23** | **34** | **73** | **148,868** |

---

## 🔴 Phase 0 — Eliminación de Duplicados (Pre-requisito)

**Prioridad**: 🚨 CRÍTICA — Hacer PRIMERO  
**Estimación**: 1-2 días  
**Líneas recuperadas**: ~26,839

Los siguientes directorios son **copias casi idénticas** de `gateway/src/lib/`:

| Directorio a ELIMINAR | Equivalente en `gateway/src/lib/` | Archivos | Líneas |
|----------------------|----------------------------------|----------|--------|
| `gateway/policy-engine/` | `gateway/src/lib/policy-engine/` | 17 | 14,069 |
| `gateway/hitl/` | `gateway/src/lib/hitl/` | 14 | 6,346 |
| `gateway/playbooks/` | `gateway/src/lib/playbooks/` | 10 | 6,424 |

### Acciones Phase 0:
1. Verificar que `gateway/src/lib/` es la versión canónica (más líneas = más actualizada)
2. Buscar todos los imports que apunten a las rutas duplicadas
3. Actualizar imports para apuntar a `gateway/src/lib/`
4. Eliminar los 3 directorios duplicados
5. Ejecutar `bun run lint` + `bun run build` para verificar

---

## 🟠 Phase 1 — Archivos Críticos (1000+ líneas)

**Prioridad**: 🔥 ALTA  
**Estimación**: 5-7 días  
**Archivos**: 31

### 1A. Gateway — TypeScript/TSX (15 archivos)

#### 1A-1. `gateway/src/app/page.tsx` — 2,804 líneas → 8 módulos

```
gateway/src/app/page/
├── index.tsx                    (~50 líneas — re-export + layout shell)
├── _dashboard_tab.tsx           (~300 líneas — tab de dashboard)
├── _safety_tab.tsx              (~300 líneas — tab de safety gate)
├── _policy_tab.tsx              (~300 líneas — tab de políticas)
├── _hitl_tab.tsx                (~300 líneas — tab de HITL)
├── _mcp_tab.tsx                 (~300 líneas — tab de MCP gateway)
├── _memory_tab.tsx              (~300 líneas — tab de memory chip)
├── _observability_tab.tsx       (~300 líneas — tab de observabilidad)
├── _subscription_tab.tsx        (~300 líneas — tab de suscripción)
└── _hooks/
    ├── use-dashboard-data.ts    (~100 líneas)
    └── use-realtime-events.ts   (~100 líneas)
```

#### 1A-2. `gateway/src/components/apis-mcp/ApisMcpTab.tsx` — 1,771 líneas → 6 módulos

```
gateway/src/components/apis-mcp/
├── ApisMcpTab.tsx               (~80 líneas — shell + tabs)
├── _server_list.tsx             (~250 líneas — lista de servidores)
├── _tool_browser.tsx            (~250 líneas — navegador de tools)
├── _call_panel.tsx              (~250 líneas — panel de llamada)
├── _approval_flow.tsx           (~250 líneas — flujo de aprobación)
├── _audit_log.tsx               (~200 líneas — log de auditoría)
└── _types.ts                    (~150 líneas — tipos compartidos)
```

#### 1A-3. `gateway/src/components/nichos/NichosSelector.tsx` — 1,291 líneas → 5 módulos

```
gateway/src/components/nichos/
├── NichosSelector.tsx           (~80 líneas — shell)
├── _niche_card.tsx              (~200 líneas)
├── _niche_config_form.tsx       (~250 líneas)
├── _onboarding_wizard.tsx       (~250 líneas)
├── _template_browser.tsx        (~200 líneas)
└── _types.ts                    (~100 líneas)
```

#### 1A-4. `gateway/src/lib/policy-engine/` — 8 archivos 1000+

| Archivo Original | Líneas | Split Propuesto |
|-----------------|--------|----------------|
| `types.ts` (1,540) | → `types/` | `types/_core.ts` (~300), `types/_policy.ts` (~300), `types/_composition.ts` (~300), `types/_simulation.ts` (~300), `types/_index.ts` (~50, re-exports) |
| `constraint-solver.ts` (1,508) | → `constraint-solver/` | `_ac3_solver.ts` (~350), `_propagation.ts` (~350), `_backtracking.ts` (~350), `_types.ts` (~150), `index.ts` (~50) |
| `impact.ts` (1,457) | → `impact/` | `_calculator.ts` (~350), `_scoring.ts` (~350), `_report.ts` (~300), `_types.ts` (~150), `index.ts` (~50) |
| `templates.ts` (1,366) | → `templates/` | `_crud.ts` (~300), `_instantiation.ts` (~300), `_validation.ts` (~300), `_types.ts` (~150), `index.ts` (~50) |
| `simulator.ts` (1,317) | → `simulator/` | `_engine.ts` (~350), `_scenarios.ts` (~350), `_results.ts` (~300), `_types.ts` (~150), `index.ts` (~50) |
| `namespaces.ts` (1,317) | → `namespaces/` | `_hierarchy.ts` (~350), `_resolution.ts` (~350), `_evaluation.ts` (~300), `_types.ts` (~150), `index.ts` (~50) |
| `conflict-detector.ts` (1,249) | → `conflict-detector/` | `_detection.ts` (~350), `_resolution.ts` (~350), `_reporting.ts` (~250), `_types.ts` (~100), `index.ts` (~50) |
| `composition.ts` (1,036) | → `composition/` | `_compose.ts` (~350), `_merge.ts` (~300), `_validate.ts` (~200), `_types.ts` (~100), `index.ts` (~50) |
| `approval.ts` (1,024) | → `approval/` | `_workflow.ts` (~350), `_decide.ts` (~300), `_deploy.ts` (~200), `_types.ts` (~100), `index.ts` (~50) |

#### 1A-5. `gateway/src/lib/playbooks/engine.ts` — 1,023 líneas → 4 módulos

```
gateway/src/lib/playbooks/engine/
├── index.ts                     (~50 líneas — re-exports)
├── _executor.ts                 (~300 líneas — ejecución de playbooks)
├── _lifecycle.ts                (~300 líneas — activar/desactivar)
├── _evaluation.ts               (~250 líneas — evaluación/compliance)
└── _types.ts                    (~150 líneas)
```

#### 1A-6. `gateway/src/lib/playbooks/yaml-loader.ts` — 997 líneas → 4 módulos

```
gateway/src/lib/playbooks/yaml-loader/
├── index.ts                     (~50 líneas)
├── _parser.ts                   (~300 líneas)
├── _validator.ts                (~300 líneas)
├── _transformer.ts              (~250 líneas)
└── _types.ts                    (~100 líneas)
```

#### 1A-7. `gateway/src/lib/pricing-engine/saga.ts` — 1,402 líneas → 5 módulos

```
gateway/src/lib/pricing-engine/saga/
├── index.ts                     (~50 líneas)
├── _orchestrator.ts             (~300 líneas)
├── _compensation.ts             (~300 líneas)
├── _steps.ts                    (~350 líneas)
├── _types.ts                    (~200 líneas)
└── _state.ts                    (~200 líneas)
```

#### 1A-8. `gateway/rust-engine/src/saga.rs` — 1,173 líneas → 4 módulos

```
gateway/rust-engine/src/saga/
├── mod.rs                       (~50 líneas — re-exports)
├── orchestrator.rs              (~300 líneas)
├── compensation.rs              (~300 líneas)
├── steps.rs                     (~300 líneas)
└── types.rs                     (~200 líneas)
```

#### 1A-9. `gateway/src/lib/pricing-engine/wasm-bridge.ts` — 964 líneas → 3 módulos

```
gateway/src/lib/pricing-engine/wasm-bridge/
├── index.ts                     (~50 líneas)
├── _loader.ts                   (~350 líneas)
├── _executor.ts                 (~350 líneas)
└── _types.ts                    (~200 líneas)
```

#### 1A-10. `gateway/src/lib/playbooks/compliance-map.ts` — 960 líneas → 3 módulos

```
gateway/src/lib/playbooks/compliance-map/
├── index.ts                     (~50 líneas)
├── _mapper.ts                   (~400 líneas)
├── _validator.ts                (~300 líneas)
└── _types.ts                    (~200 líneas)
```

#### 1A-11. `gateway/src/lib/hitl/types.ts` — 879 líneas → 3 módulos

```
gateway/src/lib/hitl/types/
├── index.ts                     (~50 líneas)
├── _core.ts                     (~350 líneas)
├── _workflow.ts                 (~300 líneas)
└── _api.ts                      (~200 líneas)
```

#### 1A-12. `gateway/src/lib/hitl/approval-engine.ts` — 877 líneas → 3 módulos

```
gateway/src/lib/hitl/approval-engine/
├── index.ts                     (~50 líneas)
├── _engine.ts                   (~350 líneas)
├── _routing.ts                  (~300 líneas)
└── _types.ts                    (~200 líneas)
```

#### 1A-13. `gateway/src/app/api/seed/route.ts` — 739 líneas → 3 módulos

```
gateway/src/app/api/seed/
├── route.ts                     (~50 líneas — handler que delega)
├── _seed_policies.ts            (~250 líneas)
├── _seed_roles.ts               (~250 líneas)
└── _seed_playbooks.ts           (~200 líneas)
```

#### 1A-14. `gateway/src/components/ui/sidebar.tsx` — 726 líneas → 3 módulos

```
gateway/src/components/ui/sidebar/
├── sidebar.tsx                  (~80 líneas)
├── _sidebar_content.tsx         (~300 líneas)
├── _sidebar_footer.tsx          (~200 líneas)
└── _types.ts                    (~100 líneas)
```

---

### 1B. Python — src/core (6 archivos)

#### 1B-1. `src/core/channels/providers/push.py` — 1,974 líneas → 7 módulos

```
src/core/channels/providers/push/
├── __init__.py                  (~50 líneas — re-exports)
├── _core.py                     (~300 líneas — PushProvider base)
├── _fcm.py                      (~300 líneas — Firebase Cloud Messaging)
├── _apns.py                     (~300 líneas — Apple Push Notification Service)
├── _web_push.py                 (~300 líneas — Web Push)
├── _batch.py                    (~300 líneas — envío batch)
├── _templates.py                (~250 líneas — templates de notificación)
└── _types.py                    (~100 líneas — tipos compartidos)
```

#### 1B-2. `src/core/executors/impact_preview.py` — 1,472 líneas → 5 módulos

```
src/core/executors/impact_preview/
├── __init__.py                  (~50 líneas)
├── _calculator.py               (~300 líneas — cálculo de impacto)
├── _previewer.py                (~300 líneas — generación de preview)
├── _report.py                   (~300 líneas — reporte de impacto)
├── _diff.py                     (~250 líneas — diff de cambios)
└── _types.py                    (~100 líneas)
```

#### 1B-3. `src/core/executors/jira_executor.py` — 1,276 líneas → 5 módulos

```
src/core/executors/jira_executor/
├── __init__.py                  (~50 líneas)
├── _executor.py                 (~300 líneas — JiraExecutor principal)
├── _issues.py                   (~300 líneas — CRUD de issues)
├── _transitions.py              (~250 líneas — transiciones de workflow)
├── _comments.py                 (~200 líneas — comentarios/attachments)
└── _types.py                    (~100 líneas)
```

#### 1B-4. `src/core/executors/servicenow_executor.py` — 1,214 líneas → 5 módulos

```
src/core/executors/servicenow_executor/
├── __init__.py                  (~50 líneas)
├── _executor.py                 (~300 líneas — ServiceNowExecutor)
├── _incidents.py                (~300 líneas — gestión de incidentes)
├── _changes.py                  (~250 líneas — gestión de cambios)
├── _catalog.py                  (~200 líneas — service catalog)
└── _types.py                    (~100 líneas)
```

#### 1B-5. `src/core/autopilot/engine.py` — 1,009 líneas → 4 módulos

```
src/core/autopilot/engine/
├── __init__.py                  (~50 líneas)
├── _core.py                     (~300 líneas — AutopilotEngine principal)
├── _decisions.py                (~300 líneas — toma de decisiones)
├── _monitoring.py               (~250 líneas — monitoreo de objetivos)
└── _types.py                    (~100 líneas)
```

#### 1B-6. `src/core/channels/_formatter.py` — 1,004 líneas → 4 módulos

```
src/core/channels/_formatter/
├── __init__.py                  (~50 líneas)
├── _message.py                  (~300 líneas — formateo de mensajes)
├── _rich.py                     (~300 líneas — formato rich/media)
├── _templates.py                (~250 líneas — templates de formato)
└── _types.py                    (~100 líneas)
```

---

### 1C. Rust — zenic-v2 (10 archivos)

#### 1C-1. `zenic-pybridge/src/certifier.rs` — 2,194 líneas → 7 módulos

```
zenic-v2/zenic-pybridge/src/certifier/
├── mod.rs                       (~50 líneas — re-exports)
├── validation.rs                (~300 líneas — validación de certificaciones)
├── issuance.rs                  (~300 líneas — emisión de certificados)
├── renewal.rs                   (~300 líneas — renovación)
├── revocation.rs                (~300 líneas — revocación)
├── audit.rs                     (~300 líneas — auditoría)
├── compliance.rs                (~300 líneas — compliance checks)
└── types.rs                     (~300 líneas — tipos compartidos)
```

#### 1C-2. `zenic-pybridge/src/completer.rs` — 2,065 líneas → 7 módulos

```
zenic-v2/zenic-pybridge/src/completer/
├── mod.rs                       (~50 líneas)
├── engine.rs                    (~300 líneas)
├── suggestions.rs               (~300 líneas)
├── ranking.rs                   (~300 líneas)
├── context.rs                   (~300 líneas)
├── templates.rs                 (~300 líneas)
├── validation.rs                (~300 líneas)
└── types.rs                     (~200 líneas)
```

#### 1C-3. `zenic-pybridge/src/safety_gate_extended.rs` — 1,363 líneas → 5 módulos

```
zenic-v2/zenic-pybridge/src/safety_gate_extended/
├── mod.rs                       (~50 líneas)
├── extended_rules.rs            (~300 líneas)
├── context_analysis.rs          (~300 líneas)
├── override_handling.rs         (~300 líneas)
├── audit_trail.rs               (~250 líneas)
└── types.rs                     (~200 líneas)
```

#### 1C-4. `zenic-pybridge/src/catalog.rs` — 1,360 líneas → 5 módulos

```
zenic-v2/zenic-pybridge/src/catalog/
├── mod.rs                       (~50 líneas)
├── registry.rs                  (~300 líneas)
├── lookup.rs                    (~300 líneas)
├── versioning.rs                (~300 líneas)
├── search.rs                    (~250 líneas)
└── types.rs                     (~200 líneas)
```

#### 1C-5. `zenic-flow/src/engine.rs` — 1,293 líneas → 5 módulos

```
zenic-v2/zenic-flow/src/engine/
├── mod.rs                       (~50 líneas)
├── execution.rs                 (~300 líneas)
├── scheduling.rs                (~300 líneas)
├── state_machine.rs             (~300 líneas)
├── hooks.rs                     (~250 líneas)
└── types.rs                     (~200 líneas)
```

#### 1C-6. `zenic-pybridge/src/license.rs` — 1,260 líneas → 5 módulos

```
zenic-v2/zenic-pybridge/src/license/
├── mod.rs                       (~50 líneas)
├── validation.rs                (~300 líneas)
├── generation.rs                (~300 líneas)
├── binding.rs                   (~300 líneas)
├── enforcement.rs               (~250 líneas)
└── types.rs                     (~200 líneas)
```

#### 1C-7. `zenic-pybridge/src/extractor.rs` — 1,219 líneas → 4 módulos

```
zenic-v2/zenic-pybridge/src/extractor/
├── mod.rs                       (~50 líneas)
├── parsing.rs                   (~350 líneas)
├── transformation.rs            (~350 líneas)
├── validation.rs                (~300 líneas)
└── types.rs                     (~200 líneas)
```

#### 1C-8. `zenic-pybridge/src/ingest.rs` — 1,197 líneas → 4 módulos

```
zenic-v2/zenic-pybridge/src/ingest/
├── mod.rs                       (~50 líneas)
├── pipeline.rs                  (~350 líneas)
├── normalization.rs             (~350 líneas)
├── enrichment.rs                (~300 líneas)
└── types.rs                     (~200 líneas)
```

#### 1C-9. `zenic-pybridge/src/safety_gate.rs` — 1,063 líneas → 4 módulos

```
zenic-v2/zenic-pybridge/src/safety_gate/
├── mod.rs                       (~50 líneas)
├── gate.rs                      (~350 líneas)
├── rules.rs                     (~350 líneas)
├── evaluation.rs                (~250 líneas)
└── types.rs                     (~200 líneas)
```

#### 1C-10. `zenic-pybridge/src/niche.rs` — 1,012 líneas → 4 módulos

```
zenic-v2/zenic-pybridge/src/niche/
├── mod.rs                       (~50 líneas)
├── registry.rs                  (~300 líneas)
├── loader.rs                    (~300 líneas)
├── validation.rs                (~250 líneas)
└── types.rs                     (~200 líneas)
```

---

## 🟡 Phase 2 — Archivos Altos (800-999 líneas)

**Prioridad**: 🟠 ALTA  
**Estimación**: 4-5 días  
**Archivos**: 23

### 2A. Python — 9 archivos

| Archivo | Líneas | Split Propuesto |
|---------|--------|----------------|
| `executors/coordinated_rollback.py` (997) | → `coordinated_rollback/` | `_coordinator.py` (~350), `_phases.py` (~350), `_compensation.py` (~200), `_types.py` (~100) |
| `native/__init__.py` (985) | → `native/` | `_loader.py` (~350), `_bindings.py` (~350), `_fallbacks.py` (~200), `__init__.py` (~50, re-exports) |
| `observability/forensic.py` (923) | → `forensic/` | `_analyzer.py` (~350), `_collector.py` (~350), `_reporter.py` (~200), `_types.py` (~100) |
| `executors/diff_preview.py` (873) | → `diff_preview/` | `_generator.py` (~350), `_formatter.py` (~300), `_comparator.py` (~200), `_types.py` (~100) |
| `executors/db_journal.py` (866) | → `db_journal/` | `_writer.py` (~350), `_reader.py` (~300), `_snapshot.py` (~200), `_types.py` (~100) |
| `agents/compat.py` (835) | → `agents/compat/` | `_adapter.py` (~350), `_mapper.py` (~300), `_migration.py` (~200), `_types.py` (~100) |
| `workflows/chain_templates.py` (827) | → `chain_templates/` | `_loader.py` (~300), `_renderer.py` (~300), `_validator.py` (~200), `_types.py` (~100) |
| `workflows/chain_composer.py` (818) | → `chain_composer/` | `_composer.py` (~300), `_optimizer.py` (~300), `_validator.py` (~200), `_types.py` (~100) |
| `autopilot/planner.py` (803) | → `autopilot/planner/` | `_planner.py` (~300), `_scheduler.py` (~300), `_optimizer.py` (~200), `_types.py` (~100) |

### 2B. TypeScript — 8 archivos

| Archivo | Líneas | Split Propuesto |
|---------|--------|----------------|
| `lib/playbooks/yaml-loader.ts` (997) | → `yaml-loader/` | Ya detallado en Phase 1 |
| `lib/pricing-engine/wasm-bridge.ts` (964) | → `wasm-bridge/` | Ya detallado en Phase 1 |
| `lib/playbooks/compliance-map.ts` (960) | → `compliance-map/` | Ya detallado en Phase 1 |
| `lib/hitl/types.ts` (879) | → `types/` | Ya detallado en Phase 1 |
| `lib/hitl/approval-engine.ts` (877) | → `approval-engine/` | Ya detallado en Phase 1 |
| `lib/playbooks/types.ts` (810) | → `types/` | `_core.ts` (~300), `_playbook.ts` (~300), `_metrics.ts` (~200), `index.ts` (~50) |
| `rust-engine/src/saga.rs` (1,173) | → `saga/` | Ya detallado en Phase 1 |
| `lib/hitl/hitl-coordinator.ts` (605) | → `hitl-coordinator/` | `_coordinator.ts` (~250), `_routing.ts` (~200), `_types.ts` (~100), `index.ts` (~50) |

### 2C. Rust — 6 archivos

| Archivo | Líneas | Split Propuesto |
|---------|--------|----------------|
| `zenic-pybridge/src/e2e_pipeline.rs` (958) | → `e2e_pipeline/` | `stages.rs` (~300), `execution.rs` (~300), `validation.rs` (~250), `types.rs` (~200) |
| `zenic-memory/src/lifecycle.rs` (938) | → `lifecycle/` | `manager.rs` (~300), `transitions.rs` (~300), `persistence.rs` (~250), `types.rs` (~200) |
| `zenic-policy/src/engine.rs` (902) | → `engine/` | `evaluator.rs` (~300), `compiler.rs` (~300), `optimizer.rs` (~250), `types.rs` (~200) |
| `zenic-pybridge/src/bus.rs` (894) | → `bus/` | `publisher.rs` (~300), `subscriber.rs` (~300), `routing.rs` (~250), `types.rs` (~200) |
| `zenic-pybridge/src/memory_chip.rs` (840) | → `memory_chip/` | `store.rs` (~300), `retrieval.rs` (~300), `lifecycle.rs` (~200), `types.rs` (~200) |
| `zenic-subscription/src/types.rs` (814) | → `types/` | `core.rs` (~300), `plan.rs` (~300), `billing.rs` (~200), `mod.rs` (~50) |

---

## 🔵 Phase 3 — Archivos Medios (600-799 líneas)

**Prioridad**: 🟡 MEDIA  
**Estimación**: 5-7 días  
**Archivos**: 34

### 3A. Python — 24 archivos

**Subsistema executors** (3 archivos):
| Archivo | Líneas | Split |
|---------|--------|-------|
| `policy_engine.py` (777) | → `policy_engine/` | `_engine.py` (~300), `_evaluator.py` (~300), `_types.py` (~100) |
| `email_parts/graph_api.py` (699) | → `graph_api/` | `_client.py` (~300), `_operations.py` (~300), `_types.py` (~100) |
| `email_parts/oauth2.py` (683) | → `oauth2/` | `_flow.py` (~300), `_token_manager.py` (~300), `_types.py` (~100) |
| `email_executor.py` (607) | → `email_executor/` | `_executor.py` (~300), `_composer.py` (~300), `_types.py` (~100) |
| `simulation_engine.py` (682) | → `simulation_engine/` | `_engine.py` (~300), `_runner.py` (~300), `_types.py` (~100) |
| `safety_gate/domain_gate.py` (633) | → `domain_gate/` | `_gate.py` (~300), `_rules.py` (~300), `_types.py` (~100) |
| `dispatch_action.py` (547) | → `dispatch_action/` | `_dispatcher.py` (~300), `_router.py` (~200), `_types.py` (~100) |
| `dry_run_executor.py` (534) | → `dry_run_executor/` | `_executor.py` (~300), `_simulator.py` (~200), `_types.py` (~100) |

**Subsistema approval** (4 archivos):
| Archivo | Líneas | Split |
|---------|--------|-------|
| `escalation.py` (724) | → `escalation/` | `_escalator.py` (~300), `_routing.py` (~300), `_types.py` (~100) |
| `rollback.py` (632) | → `rollback/` | `_manager.py` (~300), `_snapshots.py` (~300), `_types.py` (~100) |
| `notification.py` (606) | → `notification/` | `_notifier.py` (~300), `_templates.py` (~300), `_types.py` (~100) |
| `chain.py` (605) | → `chain/` | `_chain.py` (~300), `_validation.py` (~300), `_types.py` (~100) |

**Subsistema autopilot** (3 archivos):
| Archivo | Líneas | Split |
|---------|--------|-------|
| `kpi_tracker.py` (677) | → `kpi_tracker/` | `_tracker.py` (~300), `_aggregator.py` (~300), `_types.py` (~100) |
| `objective.py` (603) | → `objective/` | `_manager.py` (~300), `_scoring.py` (~300), `_types.py` (~100) |

**Subsistema channels** (4 archivos):
| Archivo | Líneas | Split |
|---------|--------|-------|
| `_registry.py` (716) | → `_registry/` | `_registry.py` (~300), `_discovery.py` (~300), `_types.py` (~100) |
| `providers/email.py` (670) | → `email/` | `_sender.py` (~300), `_templates.py` (~300), `_types.py` (~100) |
| `providers/twilio_sms.py` (622) | → `twilio_sms/` | `_sender.py` (~300), `_webhook.py` (~300), `_types.py` (~100) |
| `providers/whatsapp.py` (621) | → `whatsapp/` | `_sender.py` (~300), `_webhook.py` (~300), `_types.py` (~100) |

**Subsistema conversational** (1):
| Archivo | Líneas | Split |
|---------|--------|-------|
| `confirm_manager.py` (752) | → `confirm_manager/` | `_manager.py` (~300), `_flow.py` (~300), `_types.py` (~100) |

**Otros Python 600-799** (8 archivos):
| Archivo | Líneas | Split |
|---------|--------|-------|
| `__init__.py` (739) | → reestructurar imports | Mover exports a sub-módulos |
| `observability/snapshot_audit.py` (733) | → `snapshot_audit/` | `_snapshot.py` (~300), `_audit.py` (~300), `_types.py` (~100) |
| `events/replay_queue.py` (731) | → `replay_queue/` | `_queue.py` (~300), `_replay.py` (~300), `_types.py` (~100) |
| `agents/business/interactive_data_collector.py` (688) | → `interactive_data_collector/` | `_collector.py` (~300), `_forms.py` (~300), `_types.py` (~100) |
| `orchestration/.../compliance_checker.py` (685) | → `compliance_checker/` | `_checker.py` (~300), `_rules.py` (~300), `_types.py` (~100) |
| `agents/pipeline_orchestrator/niche_onboarding_pipeline.py` (613) | → `niche_onboarding_pipeline/` | `_pipeline.py` (~300), `_steps.py` (~300), `_types.py` (~100) |
| `exceptions/routing.py` (621) | → `routing/` | `_router.py` (~300), `_handlers.py` (~300), `_types.py` (~100) |
| `niche_rust/certifier_bridge.py` (574) | → `certifier_bridge/` | `_bridge.py` (~300), `_pyo3_bindings.py` (~250), `_types.py` (~100) |

### 3B. TypeScript — 5 archivos

| Archivo | Líneas | Split |
|---------|--------|-------|
| `lib/hitl/hitl-coordinator.ts` (605) | → `hitl-coordinator/` | `_coordinator.ts` (~250), `_routing.ts` (~200), `_types.ts` (~100) |
| `lib/hitl/reversible-action.ts` (603) | → `reversible-action/` | `_action.ts` (~250), `_undo.ts` (~200), `_types.ts` (~100) |
| `lib/playbooks/onboarding-wizard.ts` (659) | → `onboarding-wizard/` | `_wizard.ts` (~250), `_steps.ts` (~250), `_types.ts` (~100) |
| `lib/pricing-engine/types.ts` (615) | → `types/` | `_core.ts` (~250), `_saga.ts` (~250), `index.ts` (~50) |
| `api/seed/route.ts` (739) | → `seed/` | Ya detallado en Phase 1 |

### 3C. Rust — 5 archivos

| Archivo | Líneas | Split |
|---------|--------|-------|
| `zenic-core/src/orchestrator.rs` (772) | → `orchestrator/` | `coordinator.rs` (~300), `lifecycle.rs` (~300), `types.rs` (~200) |
| `zenic-pybridge/src/template.rs` (693) | → `template/` | `loader.rs` (~300), `renderer.rs` (~300), `types.rs` (~200) |
| `zenic-memory/src/types.rs` (675) | → `types/` | `core.rs` (~300), `lifecycle.rs` (~250), `mod.rs` (~50) |
| `zenic-policy/src/role.rs` (641) | → `role/` | `manager.rs` (~300), `permissions.rs` (~300), `types.rs` (~200) |
| `zenic-safety/src/domain_rules.rs` (626) | → `domain_rules/` | `loader.rs` (~300), `evaluator.rs` (~300), `types.rs` (~200) |

---

## 🟢 Phase 4 — Archivos Bajos (400-599 líneas)

**Prioridad**: 🟢 BAJA (pero necesaria)  
**Estimación**: 7-10 días  
**Archivos**: 73

> Muchos de estos archivos están cerca del límite y solo necesitan una separación básica de tipos o helpers.

### Patrón General para 400-599 líneas

Para archivos de 400-599 líneas, el split sigue este patrón:

**Python:**
```
archivo.py → archivo/
├── __init__.py     (~50 líneas, re-exports)
├── _core.py        (~250 líneas, lógica principal)
└── _types.py       (~100 líneas, tipos)
```

**TypeScript:**
```
archivo.ts → archivo/
├── index.ts        (~50 líneas, re-exports)
├── _core.ts        (~250 líneas, lógica principal)
└── _types.ts       (~100 líneas, tipos)
```

**Rust:**
```
archivo.rs → archivo/
├── mod.rs          (~50 líneas, re-exports)
├── core.rs         (~250 líneas, lógica principal)
└── types.rs        (~100 líneas, tipos)
```

### 4A. Python 400-599 — 45 archivos

| Subsistema | Archivos | Líneas totales |
|-----------|----------|---------------|
| approval | batch (597), delegation (584), audit_merkle (564), expiry (539), risk_routing (514), justification (499), adaptive (407) | 3,704 |
| autopilot | feedback (578), autonomy (485) | 1,063 |
| channels | slack (557), teams (471) | 1,028 |
| niche_rust | bridge (561), ingest_bridge (526), document_parser (432), e2e_bridge (408) | 1,927 |
| workflows | inter_workflow (570), conditional_branch (477) | 1,047 |
| exceptions | analytics (569), engine (563) | 1,132 |
| events | trigger_map (566) | 566 |
| executors | dispatch_action (547), dry_run_executor (534) | 1,081 |
| roi | impact_scorer (545), value_tracker (502), cost_accumulator (472), dashboard_data (577) | 2,096 |
| blueprints | converter (539) | 539 |
| knowledge | graph_engine (527) | 527 |
| policy_code | engine (527) | 527 |
| orchestration | dag_builder (530), state_tracker (459), progress_monitor (437) | 1,426 |
| conversational | memory_v2/engine (486), llm_translator (464), llm_drafter (423), tools/manager (414) | 1,787 |
| learning | learning_engine (474) | 474 |
| chaos | experiment_runner (491) | 491 |
| shared | z3_parts/type_safety (416) | 416 |
| verdict_parts | verdict_engine/__init__ (415) | 415 |
| code_gen_parts | smart_chain/_templates_mixin (412) | 412 |
| sna | sna_engine (431) | 431 |
| risk | engine (430) | 430 |
| degraded_mode | manager (429) | 429 |

### 4B. TypeScript 400-599 — 26 archivos

| Subsistema | Archivos | Líneas totales |
|-----------|----------|---------------|
| policy-engine | yaml-loader (478), evaluator (444) | 922 |
| playbooks | certification (599), metrics-collector (561), pricing-engine (533) | 1,693 |
| hitl | delegation (586), approval-audit (426), expiry-service (411), sla-service (410), notifications (408) | 2,241 |
| pricing-engine | types (615) | 615 |
| subscription | types (523) | 523 |
| mcp-gateway | types/index (472), adapters/native-adapter (434) | 906 |
| observability | tracing/trace-collector (449) | 449 |
| components | ui/sidebar (726) | 726 |

### 4C. Rust 400-599 — 16 archivos

| Crate | Archivos | Líneas totales |
|-------|----------|---------------|
| zenic-pybridge | risk (593), simulation (527), forensic (522), rollback (409) | 2,051 |
| zenic-safety | compliance (593), engine (524) | 1,117 |
| zenic-subscription | payment (588), engine (583) | 1,171 |
| zenic-policy | rule (552), gate (538), audit (442) | 1,532 |
| zenic-memory | ontology (474), graph (423) | 897 |
| zenic-runtime | memory (447), loader (423) | 870 |
| zenic-graph | catalog (456) | 456 |
| gateway/rust-engine | types.rs (464) | 464 |

---

## 📋 Cronograma de Ejecución

| Phase | Prioridad | Archivos | Días Estimados | Predecesor |
|-------|-----------|----------|---------------|------------|
| **Phase 0** | 🚨 CRÍTICA | 41 (eliminar) | 1-2 días | — |
| **Phase 1** | 🔥 ALTA | 31 (dividir) | 5-7 días | Phase 0 |
| **Phase 2** | 🟠 ALTA | 23 (dividir) | 4-5 días | Phase 1 |
| **Phase 3** | 🟡 MEDIA | 34 (dividir) | 5-7 días | Phase 2 |
| **Phase 4** | 🟢 BAJA | 73 (dividir) | 7-10 días | Phase 3 |
| **TOTAL** | | **202 operaciones** | **22-31 días** | |

---

## 🔄 Reglas de Refactorización (Aplicar a TODAS las Phases)

### Para Python (src/core/):
1. **Siempre crear `__init__.py`** que re-exporte la API pública original
2. **Usar el patrón mixin** cuando una clase es muy grande (ej: `_core_mixin.py`, `_extra_mixin.py`)
3. **Los tipos van en `_types.py`** separados de la lógica
4. **Imports relativos** dentro de la sub-carpeta
5. **Verificar** que `from src.core.X import Y` siga funcionando

### Para TypeScript (gateway/):
1. **Siempre crear `index.ts`** que re-exporte la API pública
2. **Separar `types.ts`** de la lógica de negocio
3. **Los componentes React** se dividen en sub-componentes con `_` prefijo
4. **Las API routes** delegan a servicios en `_services.ts`
5. **Verificar** con `bun run lint` + `bun run build`

### Para Rust (zenic-v2/):
1. **Siempre crear `mod.rs`** con `pub mod` declarations
2. **Tipos compartidos** en `types.rs` dentro del módulo
3. **El `mod.rs`** solo re-exports con `pub use`
4. **Cada sub-módulo** es un archivo `.rs` independiente
5. **Verificar** con `cargo check` + `cargo clippy`

---

## ✅ Checklist de Verificación Post-Refactorización

Después de cada Phase:

- [ ] Todos los imports existentes siguen funcionando
- [ ] Ningún archivo supera 400 líneas (excepto límites por lenguaje)
- [ ] Los tests existentes pasan (si los hay)
- [ ] `pyright` reporta 0 errores nuevos
- [ ] `bun run lint` pasa sin errores nuevos
- [ ] `cargo check` pasa sin errores nuevos
- [ ] La API pública no cambió (backward compatible)
- [ ] Se actualizó el `worklog.md` con los cambios

---

## 📈 Métricas Objetivo

| Métrica | Antes | Después |
|---------|-------|---------|
| Archivos 400+ líneas | 194 | **0** |
| Líneas duplicadas | 26,839 | **0** |
| Archivo más largo | 2,804 líneas | **< 400 líneas** |
| Promedio por archivo | ~85 líneas | ~85 líneas (más archivos, mismo total) |
| Total archivos | ~800+ | ~1,200+ |

---

*Documento generado para Zenic-Agents v3.0.0 — Plan de Modularización*
