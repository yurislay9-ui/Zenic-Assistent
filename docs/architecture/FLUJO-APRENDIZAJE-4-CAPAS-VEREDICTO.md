# FLUJO DE APRENDIZAJE BAJO LAS 4 CAPAS DEL VEREDICTO — Zenic-Agents v3.0.0

## Restricciones Físicas Inviolables

- **Offline**: Sin cloud, sin APIs externas
- **CPU-only**: Sin GPU
- **ARM64**: Android/Termux como plataforma target
- **500MB RAM mínimo**
- **Modelo local**: Qwen3-0.6B
- **Invariante 1 y 2**: El LLM NUNCA genera contenido, solo emite veredicto booleano

## Tecnología Descartada

❌ Bases de datos vectoriales en la nube
❌ Grafos pesados (Neo4j, etc.)
❌ Almacenamiento agéntico comercial
❌ Cualquier servicio que requiera red externa

## Estructura de la Memoria en Zenic

El conocimiento evolutivo NO altera los pesos del LLM. Modifica determinísticamente la configuración del **DAG Fractal de 121 nodos** y del **Policy Engine**.

### Componente 1: Persistencia Base en SQLite

Administrada por `policy_code/`. Contiene:
- Políticas base de control
- Tablas de relaciones operativas
- Mapeos verificados (locales, sin cloud)

### Componente 2: Capa Declarativa YAML con Hot-Reload

- Políticas en formato YAML declarativo versionable (tipo Git)
- Adición dinámica de reglas de negocio y excepciones
- Hot-reload vía `zenic-policy` (Rust crate)
- Rendimiento wire-speed

---

## El Flujo de Aprendizaje bajo las 4 Capas del Veredicto

Cuando el sistema enfrenta un escenario nuevo (ambigüedad semántica, reestructuración de esquemas, enrutamiento MCP):

### Capa 1: DeterministicPipeline

El sistema ejecuta **7 tareas determinísticas sin intervención de IA**:
- Clasificación
- Extracción
- Validación
- Detección analítica de conflictos/desalineación

Si encuentra un mapeo ya aprendido en caché local → ejecuta directo en <5ms. La IA no se enciende.

### Capa 2: EvidenceCollector

Se recolectan señales a favor y en contra de las alternativas de solución generadas por código.

### Capa 3: ConsensusResolver

Evaluación de consenso automático ponderado entre las evidencias.

### Capa 4: VerdictEngine (El Interruptor Binario)

**Solo si hay empate o falta de consenso**, interviene Qwen3-0.6B:

- El motor de Rust presenta una **hipótesis binaria estricta**
- La IA responde con **un solo token booleano (SÍ/NO)**
- No genera texto, no propone soluciones

---

## Cierre de Circuito Seguro: Validación e Inmutabilidad

Tras veredicto aprobatorio (SÍ), la regla NO se inyecta directamente:

### Paso 1: HITL Obligatorio

- La propuesta pasa por `approval/` (flujo HITL)
- Se exige justificación del administrador
- Se adjunta evidencia de ejecución recolectada

### Paso 2: Compilación Determinista de Políticas

- Python renderiza la nueva regla en YAML declarativo
- `zenic-policy` (Rust) procesa y ejecuta hot-reload seguro
- No se reinicia el servicio

### Paso 3: Sellado en MerkleLedger

- Registro inmutable en bloques criptográficos
- Anti-tampering garantizado
- Hashing BLAKE3 vía `_zenic_native` (Rust)
- Raíz Merkle calculada a alta velocidad

---

## Resultado Final del Aprendizaje

La próxima vez que se presente la misma variación semántica o consulta:

1. El conflicto se resuelve en **Capa 1 (DeterministicPipeline)**
2. La capa determinista encuentra la regla YAML en caché local
3. Despacha la acción vía **MCP Gateway** en **<5ms**
4. **La IA no se enciende** — cero ciclos de procesamiento adicionales

---

## Integración con Arquitectura Existente

| Componente | Función en el Flujo de Aprendizaje |
|---|---|
| DeterministicPipeline (L1-L7) | Primera línea: resolve lo conocido sin IA |
| EvidenceCollector | Recolecta señales pro/con para hipótesis |
| ConsensusResolver | Consenso ponderado automático |
| VerdictEngine | Interruptor binario: solo empates |
| HITL (approval/) | Validación humana mandatoria |
| policy_code/ (Python) | Render YAML + SQLite persistence |
| zenic-policy (Rust) | Hot-reload de políticas |
| MerkleLedger (_zenic_native) | Sellado criptográfico BLAKE3 |
| MCP Gateway | Despacho final de acciones |

---

*Documento generado como parte de Zenic-Agents v3.0.0 — Architectural Decision Record*
