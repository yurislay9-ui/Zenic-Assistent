// ─── HITL Evidence — Evidencia HISTÓRICA desde DB ───────────────────
// FIX: Antes la evidencia era determinista por string matching — toda
// solicitud "schema_drift" recibía el mismo texto sin importar el contexto.
// Ahora: consulta historial de acciones similares + denegaciones previas
// del gateway para generar evidencia basada en datos REALES.
// Las heurísticas se mantienen solo para hechos objetivos (reversibilidad,
// prioridad) — nunca para suposiciones sobre el contenido de la acción.

import { NextResponse } from "next/server";
import { db } from "@/lib/db";

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const requestId = searchParams.get("requestId");

    if (!requestId) {
      return NextResponse.json(
        { error: "Se requiere requestId" },
        { status: 400 }
      );
    }

    // ── Obtener la solicitud HITL ────────────────────────────────────
    const hitlRequest = await db.hitlApprovalRequest.findUnique({
      where: { requestId },
    });

    if (!hitlRequest) {
      return NextResponse.json(
        { error: "Solicitud no encontrada" },
        { status: 404 }
      );
    }

    // ── Obtener decisiones previas para esta solicitud ───────────────
    const decisions = await db.hitlApprovalDecision.findMany({
      where: { requestId },
      orderBy: { decidedAt: "desc" },
    });

    // ── Parsear payloads ─────────────────────────────────────────────
    let payload: Record<string, unknown> = {};
    try {
      payload = JSON.parse(hitlRequest.actionPayload);
    } catch {
      // ignore parse errors
    }

    let metadata: Record<string, unknown> = {};
    try {
      metadata = JSON.parse(hitlRequest.metadata);
    } catch {
      // ignore parse errors
    }

    // ── Construir evidencia ──────────────────────────────────────────
    const evidenceFor: Array<{
      point: string;
      weight: number;
      source: string;
    }> = [];
    const evidenceAgainst: Array<{
      point: string;
      weight: number;
      source: string;
    }> = [];

    // ── Evidencia #1: Veredicto LLM ──────────────────────────────────
    // Este viene del metadata de la solicitud — es un dato que el sistema
    // ya calculó, no una heurística nueva.
    const llmVerdict = (metadata?.llmVerdict as boolean) ?? false;
    if (llmVerdict) {
      evidenceFor.push({
        point: "El motor de inteligencia clasificó esta acción como segura",
        weight: 0.7,
        source: "Motor de Veredicto IA",
      });
    } else {
      evidenceAgainst.push({
        point: "El motor de inteligencia clasificó esta acción como riesgosa",
        weight: 0.8,
        source: "Motor de Veredicto IA",
      });
    }

    // ── Evidencia #2: Historial de acciones similares ────────────────
    // CUÁNTAS acciones del mismo tipo se aprobaron/rechazaron antes.
    // Esto es evidencia REAL basada en decisiones documentadas, no heurística.
    const [similarApproved, similarRejected, similarTotal] =
      await Promise.all([
        db.hitlApprovalRequest.count({
          where: {
            targetAction: hitlRequest.targetAction,
            status: "approved",
            id: { not: hitlRequest.id }, // excluir la solicitud actual
          },
        }),
        db.hitlApprovalRequest.count({
          where: {
            targetAction: hitlRequest.targetAction,
            status: "rejected",
            id: { not: hitlRequest.id },
          },
        }),
        db.hitlApprovalRequest.count({
          where: {
            targetAction: hitlRequest.targetAction,
            id: { not: hitlRequest.id },
          },
        }),
      ]);

    if (similarTotal > 0) {
      const approvalRate = similarApproved / similarTotal;
      if (approvalRate >= 0.8) {
        evidenceFor.push({
          point: `${similarApproved} de ${similarTotal} acciones "${hitlRequest.targetAction}" fueron aprobadas previamente (${Math.round(approvalRate * 100)}%)`,
          weight: Math.min(0.3 + approvalRate * 0.4, 0.7), // 0.3–0.7 según tasa
          source: "Historial de Decisiones",
        });
      } else if (approvalRate <= 0.3) {
        evidenceAgainst.push({
          point: `Solo ${similarApproved} de ${similarTotal} acciones "${hitlRequest.targetAction}" fueron aprobadas (${Math.round(approvalRate * 100)}%)`,
          weight: Math.min(0.4 + (1 - approvalRate) * 0.4, 0.8),
          source: "Historial de Decisiones",
        });
      } else {
        evidenceFor.push({
          point: `Historial mixto para "${hitlRequest.targetAction}": ${similarApproved} aprobadas, ${similarRejected} rechazadas`,
          weight: 0.2,
          source: "Historial de Decisiones",
        });
      }
    }

    // ── Evidencia #3: Reversibilidad ─────────────────────────────────
    // Hecho objetivo del sistema — no es una suposición.
    if (hitlRequest.isReversible) {
      evidenceFor.push({
        point: "La acción es reversible — se puede deshacer si es necesario",
        weight: 0.4,
        source: "Sistema de Compensación",
      });
    } else {
      evidenceAgainst.push({
        point: "La acción es IRREVERSIBLE — no se puede deshacer",
        weight: 0.9,
        source: "Sistema de Compensación",
      });
    }

    // ── Evidencia #4: Bloqueos previos del gateway ───────────────────
    // Cuántas veces el gateway denegó acceso a este recurso antes.
    // Esto es un indicador objetivo del riesgo histórico del recurso.
    const priorDenials = await db.toolExecution.count({
      where: {
        verdict: "deny",
        verdictReason: { contains: hitlRequest.targetResource },
        createdAt: {
          gte: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000), // últimos 30 días
        },
      },
    });

    if (priorDenials > 0) {
      evidenceAgainst.push({
        point: `El gateway bloqueó ${priorDenials} acceso${priorDenials > 1 ? "s" : ""} a "${hitlRequest.targetResource}" en los últimos 30 días`,
        weight: Math.min(0.3 + priorDenials * 0.1, 0.8),
        source: "Security Gate",
      });
    }

    // ── Evidencia #5: Prioridad ──────────────────────────────────────
    // Hecho objetivo — la prioridad la asigna el sistema, no es heurística.
    if (
      hitlRequest.priority === "high" ||
      hitlRequest.priority === "critical"
    ) {
      evidenceAgainst.push({
        point: `Prioridad ${hitlRequest.priority} — impacto potencial alto`,
        weight: hitlRequest.priority === "critical" ? 0.7 : 0.5,
        source: "Evaluador de Riesgo",
      });
    }

    // ── Categoría de acción para color coding ────────────────────────
    let actionCategory = "safe";
    if (
      hitlRequest.targetAction?.includes("financial") ||
      hitlRequest.targetAction?.includes("payment") ||
      (hitlRequest.type === "data_access" &&
        hitlRequest.targetResource?.includes("financial"))
    ) {
      actionCategory = "financial";
    }
    if (
      hitlRequest.targetAction?.includes("delete") ||
      hitlRequest.targetAction?.includes("destructive") ||
      hitlRequest.priority === "critical"
    ) {
      actionCategory = "destructive";
    }

    return NextResponse.json({
      requestId: hitlRequest.requestId,
      title: hitlRequest.title,
      description: hitlRequest.description,
      status: hitlRequest.status,
      priority: hitlRequest.priority,
      type: hitlRequest.type,
      category: actionCategory,
      requesterName: hitlRequest.requesterName,
      targetResource: hitlRequest.targetResource,
      targetAction: hitlRequest.targetAction,
      isReversible: hitlRequest.isReversible,
      createdAt: hitlRequest.createdAt.toISOString(),
      deadline: hitlRequest.deadline?.toISOString() ?? null,
      llmVerdict,
      evidenceFor,
      evidenceAgainst,
      // Contexto estadístico nuevo — para que el frontend pueda mostrar
      // "3 de 5 acciones similares fueron aprobadas" con datos reales
      similarActionsContext:
        similarTotal > 0
          ? {
              total: similarTotal,
              approved: similarApproved,
              rejected: similarRejected,
            }
          : null,
      decisions: decisions.map((d) => ({
        decision: d.decision,
        decisionByName: d.decisionByName,
        comment: d.comment,
        decidedAt: d.decidedAt.toISOString(),
      })),
      requiredApprovals: hitlRequest.requiredApprovals,
      currentApprovals: hitlRequest.currentApprovals,
    });
  } catch (error) {
    console.error("[/api/dashboard/hitl-evidence GET]", error);
    return NextResponse.json(
      { error: "Error al obtener evidencia" },
      { status: 500 }
    );
  }
}
