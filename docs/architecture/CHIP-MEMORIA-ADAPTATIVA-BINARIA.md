# CHIP DE MEMORIA ADAPTATIVA BINARIA — Zenic-Agents v3.0.0

## Principio Fundamental

> **La Capa Estructurada Propone, la IA Clasifica (Sí/No) y el Humano Valida.**

La IA de Zenic está estrictamente limitada a responder Sí/No. No genera texto libre. Esto elimina el 100% de las alucinaciones. La IA actúa como un **Filtro Semántico Binario de Alta Velocidad**.

El "chip" de memoria no altera el cerebro del LLM. Alimenta una **Base de Conocimiento Determinista (Grafo de Relaciones)**. El código (en Rust/Python) genera las opciones, la IA actúa como el interruptor que dice "Sí" o "No", y el sistema guarda las relaciones aprobadas.

---

## Arquitectura del "Chip Binario"

La memoria que Zenic acumula se almacena en un **Grafo de Mapeo Semántico** local (SQLite indexada o grafo embebido). Este grafo guarda registros simples de tipo:

```
Origen -> Relación -> Destino
```

que han sido validados.

---

## Los 3 Mecanismos de Aprendizaje

### Mecanismo 1: Adaptación a Cambios en la Base de Datos (Schema Drift)

Las bases de datos cambian: se añaden columnas, se renombran tablas, se reestructuran datos.

**Ejemplo:**
- El DAG Core busca `estatus_cliente` pero la columna fue renombrada a `estado_id`.
- El código detecta el error, extrae las columnas existentes.
- La IA evalúa una por una: `"¿Es 'estado_id' equivalente semántico de 'estatus_cliente'? -> SÍ"`.
- Se genera propuesta de mapeo → HITL aprueba → Se escribe en el Grafo de Memoria.
- **Aprendizaje:** La próxima vez, la capa determinista consulta el Grafo, encuentra el redireccionamiento, ejecuta correctamente en microsegundos **sin volver a preguntar a la IA**.

### Mecanismo 2: Enrutamiento Inteligente de Intenciones (MCP Gateway)

Los usuarios piden las cosas de mil maneras distintas. El MCP Gateway tiene herramientas fijas.

**Ejemplo:**
- Usuario escribe: *"Zenic, tumba la cuenta de la empresa X"*.
- El código no encuentra `tumba_cuenta`.
- La IA evalúa contra herramientas registradas: `"¿'tumba la cuenta' equivale a 'cancelar_suscripcion'? -> SÍ"`.
- Se ejecuta la acción segura + HITL: *"¿Guardar 'tumba la cuenta' como sinónimo permanente de 'cancelar_suscripcion'? [Aprobar]"*.
- **Aprendizaje:** El comando se indexa en memoria. Zenic ha "aprendido" jerga local.

### Mecanismo 3: Refinamiento de Políticas de Seguridad (Policy Engine)

El Safety Gate decide si acciones cumplen políticas en escenarios grises.

**Ejemplo:**
- Política: *"Solo gerentes pueden aprobar gastos críticos"*.
- Usuario intenta pago de $500 para "Reparación urgente del servidor".
- La IA clasifica: *"¿Reparación urgente por $500 = 'gasto crítico'? -> SÍ"*.
- Se aplica bloqueo inmediato (Fail-safe). Se registra la clasificación.
- **Aprendizaje:** El sistema categoriza semánticamente incidentes basándose en precedentes binarios.

---

## Flujo de Datos (Latencia < 5ms en Gateway)

```
[Entrada de Datos/Error]
       │
       ▼
[Capa Determinista: Python] ──(Busca en caché de memoria local)──► [¿Existe relación?] ──► SÍ ──► [Ejecuta en Rust a Wire-Speed]
       │                                                                   │
       ▼ NO                                                                ▼ NO
[Generador de Hipótesis Estructuradas]                               [Ejecuta Acción]
       │
       ▼
[Filtro IA: Evaluación SÍ/NO]
       │
       ▼ SÍ
[Módulo HITL: Validación Humana de 1-Clic]
       │
       ▼
[Escritura en Grafo de Memoria (SQLite/Local)] ──► (El sistema ya aprendió para la próxima vez)
```

### Capas del Flujo

1. **Caché de Memoria junto a Rust/Python:** La capa determinista busca en la DB de memoria local (relaciones ya aprendidas). Si existe, va directo al Core de Rust en microsegundos. La IA ni se enciende.

2. **Hot Path de Evaluación IA:** Si la relación es nueva, la IA emite veredicto (Sí/No). Respuesta de un solo token = costo computacional y latencia mínimos.

3. **Registro Inmutable:** Cada aprobación binaria (SÍ) se firma criptográficamente y se añade al MerkleLedger de auditoría. Aprendizaje auditable y reversible.

---

## Decisión Arquitectónica: Grafo de Memoria

**Decisión: Modelo Híbrido — Grafo por Tenant con Shared Ontology Layer**

- **Grafo por tenant (aislado):** Cada base de datos de usuario tiene su propio grafo de mapeos semánticos. Esto garantiza que el aprendizaje de un cliente no contamine el de otro.
- **Capa de ontología compartida (opt-in):** Un nodo centralizado que contiene mapeos "universales" validados por Zenic (ej: sinónimos comunes en español, mapeos estándar de la industria). Los tenants pueden optar por heredar estas relaciones, pero las sobreescriben localmente si tienen sus propias reglas.

**Razón:** Un grafo puramente centralizado crearía contaminación cruzada entre empresas (la jerga de un banco no aplica a un hospital). Un grafo puramente aislado desperdicia aprendizaje validado que sí es universal. El modelo híbrido maximiza la velocidad de aprendizaje sin sacrificar aislamiento.

---

## Integración con Componentes Existentes de Zenic

| Componente Zenic | Rol en el Chip Binario |
|---|---|
| MCP Gateway (8-step pipeline) | Mecanismo 2: Enrutamiento de intenciones |
| Policy Engine (Z3+AC-3) | Mecanismo 3: Refinamiento de políticas |
| DAG Core (8-level pipeline) | Mecanismo 1: Schema Drift |
| MerkleLedger | Registro inmutable de aprendizajes aprobados |
| HITL (5 approval modes) | Validación humana de 1 clic |
| Safety Gate | Filtro fail-safe antes de ejecución |
| Subscription Engine | Feature gate: mecanismos por tier |

---

*Documento generado como parte de Zenic-Agents v3.0.0 — Architectural Decision Record*
