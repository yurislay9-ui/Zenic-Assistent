// ─── Pipeline Status — Estado REAL desde Span + ToolExecution ────────
// FIX: Antes el paso "procesándose" era una rotación de reloj modular
// (cyclePosition = time % 90s), y todos los 9 pasos tenían el mismo
// throughput. Ahora: deriva el estado de cada paso desde Span reales
// (modelo que YA EXISTE en el schema Prisma). Sin datos → "idle" honesto.
// Los nombres de span se alinean con el modelo Span.name existente.
// Si los nombres reales del gateway difieren, solo hay que actualizar
// el array STEP_SPAN_NAMES — cero cambios de arquitectura.

import { NextResponse } from "next/server";
import { db } from "@/lib/db";

/**
 * Mapeo de nombres de span al paso del pipeline.
 * Los spans vienen del modelo Span (observability) que instrumenta
 * el gateway real. Si no hay spans, cada paso se deriva de ToolExecution.
 */
const STEP_SPAN_NAMES: Array<{
  id: number;
  name: string;
  description: string;
  spanNames: string[];
  icon: string;
}> = [
  {
    id: 1,
    name: "Búsqueda en Memoria",
    description: "Consulta la base de conocimiento adaptativa",
    spanNames: [
      "gateway.memory_lookup",
      "gateway.memory_search",
      "gateway.chip_retrieval",
    ],
    icon: "Database",
  },
  {
    id: 2,
    name: "Clasificación de Intención",
    description: "Identifica qué quiere hacer el usuario",
    spanNames: ["gateway.intent_classify", "gateway.intent_routing"],
    icon: "Target",
  },
  {
    id: 3,
    name: "Extracción de Entidades",
    description: "Aisla los datos clave de la solicitud",
    spanNames: ["gateway.entity_extract", "gateway.schema_extract"],
    icon: "Scissors",
  },
  {
    id: 4,
    name: "Validación de Esquema",
    description: "Verifica que los datos cumplan el formato esperado",
    spanNames: ["gateway.schema_validate", "gateway.input_validate"],
    icon: "CheckCircle",
  },
  {
    id: 5,
    name: "Adaptación del Flujo",
    description: "Ajusta parámetros sin alterar la estructura",
    spanNames: ["gateway.flow_adapt", "gateway.param_adjust"],
    icon: "Sliders",
  },
  {
    id: 6,
    name: "Verificación de Permisos",
    description: "Confirma que el usuario tiene autorización",
    spanNames: [
      "gateway.auth_check",
      "gateway.rbac_check",
      "gateway.policy_evaluate",
    ],
    icon: "Shield",
  },
  {
    id: 7,
    name: "Recolección de Contexto",
    description: "Junta toda la evidencia disponible",
    spanNames: [
      "gateway.context_gather",
      "gateway.evidence_collect",
    ],
    icon: "FolderSearch",
  },
  {
    id: 8,
    name: "Enrutamiento de Herramienta",
    description: "Dirige la solicitud al servicio correcto",
    spanNames: ["gateway.tool_resolve", "gateway.tool_route"],
    icon: "Route",
  },
  {
    id: 9,
    name: "Simulación en Seco",
    description: "Ejecuta la acción en modo prueba antes de aprobar",
    spanNames: [
      "gateway.dry_run",
      "gateway.simulate",
      "gateway.pre_execute",
    ],
    icon: "FlaskConical",
  },
];

export async function GET() {
  try {
    const now = new Date();
    const last1h = new Date(now.getTime() - 60 * 60 * 1000);

    // ── Consultar spans reales de la última hora ──────────────────────
    // Los spans son la fuente de verdad del pipeline instrumentado.
    const recentSpans = await db.span.findMany({
      where: {
        startTime: { gte: last1h },
        service: "zenic-gateway",
      },
      select: {
        name: true,
        status: true,
        duration: true,
        startTime: true,
      },
      take: 500,
      orderBy: { startTime: "desc" },
    });

    // ── Consultar ejecuciones recientes para métricas de throughput ────
    const recentExecutions = await db.toolExecution.findMany({
      where: { createdAt: { gte: last1h } },
      select: { status: true, verdict: true, createdAt: true },
      orderBy: { createdAt: "desc" },
      take: 50,
    });

    const total = recentExecutions.length;
    const isActive = total > 0;

    // ── Derivar estado de cada paso desde spans reales ────────────────
    const steps = STEP_SPAN_NAMES.map((stepDef) => {
      // Buscar spans que correspondan a este paso
      const stepSpans = recentSpans.filter((s) =>
        stepDef.spanNames.includes(s.name)
      );

      let status: "idle" | "active" | "processing" | "error" = "idle";
      let throughput = 0;
      let avgDuration: number | null = null;

      if (stepSpans.length > 0) {
        // Hay spans reales → calcular estado
        const hasError = stepSpans.some((s) => s.status === "error");
        const recentSpan = stepSpans[0]; // Ya ordenados desc por startTime

        // "processing" si el span más reciente es de los últimos 30 segundos
        const thirtySecondsAgo = new Date(now.getTime() - 30_000);
        const isRecent = recentSpan.startTime >= thirtySecondsAgo;

        if (
          hasError &&
          stepSpans.filter((s) => s.status === "error").length >
            stepSpans.length * 0.3
        ) {
          // Más del 30% de los spans tienen error → estado de error
          status = "error";
        } else if (isRecent) {
          // Span activo en los últimos 30 segundos → procesando
          status = "processing";
        } else {
          // Hay spans pero no recientes → paso activo pero no procesando ahora
          status = "active";
        }

        throughput = stepSpans.length;
        const durations = stepSpans
          .map((s) => s.duration)
          .filter((d): d is number => d !== null);
        avgDuration =
          durations.length > 0
            ? Math.round(
                durations.reduce((a, b) => a + b, 0) / durations.length
              )
            : null;
      } else if (isActive) {
        // Hay ejecuciones pero no hay spans para este paso →
        // probablemente se completó rápido o no está instrumentado aún
        status = "active";
        throughput = 0;
      }
      // Si no hay ejecuciones ni spans → "idle" (honesto, no fake)

      return {
        id: stepDef.id,
        name: stepDef.name,
        description: stepDef.description,
        icon: stepDef.icon,
        status,
        throughput,
        avgDuration,
      };
    });

    // ── Determinar "paso actual" desde datos reales ───────────────────
    // El paso actual es el que está en "processing", o el último "active"
    const currentStep =
      steps.find((s) => s.status === "processing")?.id ??
      steps
        .filter((s) => s.status === "active")
        .at(-1)?.id ??
      0;

    const completed = recentExecutions.filter(
      (e) => e.status === "completed"
    ).length;
    const denied = recentExecutions.filter(
      (e) => e.verdict === "deny"
    ).length;

    return NextResponse.json({
      steps,
      currentStep,
      isActive,
      totalProcessed: total,
      completedCount: completed,
      deniedCount: denied,
      // cycleTime eliminado — era artefacto de la simulación por reloj
    });
  } catch (error) {
    console.error("[/api/dashboard/pipeline-status GET]", error);
    return NextResponse.json(
      { error: "Error al obtener estado del pipeline" },
      { status: 500 }
    );
  }
}
