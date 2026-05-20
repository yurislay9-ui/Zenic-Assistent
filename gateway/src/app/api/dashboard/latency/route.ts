// ─── Latency Breakdown — Latencia REAL desde Span + ToolExecution ───
// FIX: Antes usaba proporciones hardcodeadas (0.5%, 0.8%, 2%) con
// Math.min() que siempre daba "good" = información falsa.
// Ahora: usa Span.duration para cada fase del gateway (datos reales).
// Si no hay spans, muestra solo avgDuration real de ToolExecution
// con etiqueta honesta (dataSource: "executions").
// Umbrales basados en la arquitectura documentada del gateway:
//   LLM Yes/No: binario, <5ms es realista
//   Policy Check: evaluación local, <3ms
//   Ejecución: depende de la herramienta externa, <100ms es good
//   Total: <150ms es el target documentado

import { NextResponse } from "next/server";
import { db } from "@/lib/db";

/** Umbrales honestos basados en la arquitectura documentada del gateway */
const THRESHOLDS = {
  llm: { good: 5, warning: 50 }, // LLM Yes/No: binario, <5ms realista
  policy: { good: 3, warning: 30 }, // Policy check: evaluación local, <3ms
  execution: { good: 100, warning: 500 }, // Ejecución: depende de herramienta
  total: { good: 150, warning: 600 }, // Total gateway overhead
} as const;

type LatencyStatus = "good" | "warning" | "critical";

function getStatus(
  value: number,
  threshold: { good: number; warning: number }
): LatencyStatus {
  if (value <= threshold.good) return "good";
  if (value <= threshold.warning) return "warning";
  return "critical";
}

/** Calcula el promedio de duración en ms desde un array de spans */
function avgMs(
  spans: Array<{ duration: number | null }>
): number | null {
  const durations = spans
    .map((s) => s.duration)
    .filter((d): d is number => d !== null);
  return durations.length > 0
    ? Math.round(
        durations.reduce((a, b) => a + b, 0) / durations.length
      )
    : null;
}

export async function GET() {
  try {
    const now = new Date();
    const last24h = new Date(now.getTime() - 24 * 60 * 60 * 1000);

    // ── Consultar spans de latencia del gateway ──────────────────────
    // Los spans tienen duración real de cada fase del pipeline.
    const gatewaySpans = await db.span.findMany({
      where: {
        service: "zenic-gateway",
        startTime: { gte: last24h },
        duration: { not: null },
      },
      select: { name: true, duration: true },
      take: 500,
      orderBy: { startTime: "desc" },
    });

    // ── Agrupar spans por categoría de latencia ──────────────────────
    const llmSpans = gatewaySpans.filter(
      (s) =>
        s.name.includes("llm") ||
        s.name.includes("verdict") ||
        s.name.includes("classify")
    );
    const policySpans = gatewaySpans.filter(
      (s) =>
        s.name.includes("policy") ||
        s.name.includes("rbac") ||
        s.name.includes("auth_check")
    );
    const execSpans = gatewaySpans.filter(
      (s) =>
        s.name.includes("execute") ||
        s.name.includes("tool_") ||
        s.name.includes("route")
    );

    const llmMs = avgMs(llmSpans);
    const policyMs = avgMs(policySpans);
    const execMs = avgMs(execSpans);

    // ── Fallback: si no hay spans, usar ToolExecution.duration ────────
    let totalOverhead: number;
    let dataSource: "spans" | "executions";

    if (llmMs !== null || policyMs !== null || execMs !== null) {
      // Tenemos datos reales de spans — usarlos
      const knownValues = [llmMs, policyMs, execMs].filter(
        (v): v is number => v !== null
      );
      totalOverhead = knownValues.reduce((a, b) => a + b, 0);
      dataSource = "spans";
    } else {
      // No hay spans → usar duración promedio de ToolExecution
      const completedExecutions = await db.toolExecution.findMany({
        where: {
          status: "completed",
          duration: { not: null },
          createdAt: { gte: last24h },
        },
        select: { duration: true },
        take: 200,
        orderBy: { createdAt: "desc" },
      });

      totalOverhead =
        completedExecutions.length > 0
          ? Math.round(
              completedExecutions.reduce(
                (sum, e) => sum + (e.duration ?? 0),
                0
              ) / completedExecutions.length
            )
          : 0;
      dataSource = "executions";
    }

    // ── Construir breakdown ──────────────────────────────────────────
    const breakdown: Array<{
      label: string;
      value: string;
      status: LatencyStatus | "target";
      ms?: number;
      source?: string;
    }> = [];

    if (dataSource === "spans") {
      // Datos reales por componente del gateway
      if (llmMs !== null) {
        breakdown.push({
          label: "LLM Yes/No",
          value: `${llmMs}ms`,
          status: getStatus(llmMs, THRESHOLDS.llm),
          ms: llmMs,
          source: "span",
        });
      }
      if (policyMs !== null) {
        breakdown.push({
          label: "Policy Check",
          value: `${policyMs}ms`,
          status: getStatus(policyMs, THRESHOLDS.policy),
          ms: policyMs,
          source: "span",
        });
      }
      if (execMs !== null) {
        breakdown.push({
          label: "Ejecución",
          value: `${execMs}ms`,
          status: getStatus(execMs, THRESHOLDS.execution),
          ms: execMs,
          source: "span",
        });
      }
    } else {
      // Solo tenemos duración total de ejecuciones — etiquetar honestamente
      breakdown.push({
        label: "Duración Promedio (ejecuciones)",
        value: totalOverhead > 0 ? `${totalOverhead}ms` : "Sin datos",
        status:
          totalOverhead > 0
            ? getStatus(totalOverhead, THRESHOLDS.total)
            : "good",
        ms: totalOverhead > 0 ? totalOverhead : undefined,
        source: "execution_avg",
      });
    }

    breakdown.push({
      label: "Total Gateway Overhead",
      value: totalOverhead > 0 ? `${totalOverhead}ms` : "Sin datos",
      status:
        totalOverhead > 0
          ? getStatus(totalOverhead, THRESHOLDS.total)
          : "good",
      ms: totalOverhead > 0 ? totalOverhead : undefined,
      source: dataSource,
    });

    breakdown.push({
      label: "Target",
      value: "<150ms",
      status: "target",
    });

    return NextResponse.json({
      breakdown,
      // "spans" (real por componente) o "executions" (promedio global)
      dataSource,
      sampleSize: gatewaySpans.length || 0,
    });
  } catch (error) {
    console.error("[/api/dashboard/latency GET]", error);
    return NextResponse.json(
      { error: "Failed to compute latency breakdown" },
      { status: 500 }
    );
  }
}
