# SERIALIZACIÓN BINARIA: rkyv + bincode — Zenic-Agents v3.0.0

## Estado Actual

**NO** están agregados `rkyv` ni `bincode` en el stack actual. `serde` + `serde_json` son las únicas herramientas de serialización en uso.

## El Cuello de Botella

La comunicación Rust ↔ Python usa **PyO3 + SharedMemoryBus**. El MCP Gateway exige wire-speed con overhead <5ms. Si se usa `serde_json` para pasar contextos de sesión, políticas complejas y registros de auditoría, se desperdician ciclos de CPU y memoria en allocation + parsing de texto en cada salto.

---

## bincode — Serialización Binaria Compacta

- Trabaja de la mano con `serde`
- Serialización/deserialización drásticamente más rápida que JSON
- Datos ocupan mucho menos espacio en memoria
- **Limitación**: Requiere deserializar (alocar memoria, crear structs, copiar datos)

### Casos de Uso en Zenic:
- **Persistencia y Auditoría**: Estados del MerkleLedger, estados de sesión en SQLCipher
- **Transmisión de red**: Reducir peso de datos entre nodos Rust
- **Checkpoint storage**: `zenic-flow` ya usa `bincode` + `zstd` para checkpoints

---

## rkyv — Deserialización Zero-Copy (RECOMENDADO)

- Acceso a estructuras directamente desde bytes serializados
- **Sin alocación de memoria ni deserialización previa**
- Costo computacional de lectura: **O(1)**

### Casos de Uso en Zenic:
- **SharedMemoryBus**: Elimina latencia de serialización inter-proceso
- **Policy Engine Hot Path**: Cargar políticas precompiladas, Safety Gate responde en microsegundos
- **DAG Core Context**: Leer variables específicas (ej: `is_approved`) directamente desde memoria compartida
- **Memory Chip Cache**: Lookup de mapeos semánticos en <1μs sin deserialización

---

## Veredicto Estratégico

| Tecnología | Uso | Razón |
|-----------|-----|-------|
| **rkyv** | SharedMemoryBus, Policy Engine hot path, DAG Core context, Memory Chip cache | Zero-copy = sin alocación = máxima velocidad |
| **bincode** | MerkleLedger storage, checkpoint persistence, audit trail | Compacto + criptográficamente amigable + serde-compatible |
| **serde_json** | Solo para APIs externas y YAML rendering | Compatibilidad humana/externa |

---

## Principio

> Reemplazar `serde_json` por `rkyv` en la memoria compartida y tránsito interno de Rust, mientras se utiliza `bincode` para el almacenamiento criptográfico inmutable (Ledger).

---

*Documento generado como parte de Zenic-Agents v3.0.0 — Architectural Decision Record*
