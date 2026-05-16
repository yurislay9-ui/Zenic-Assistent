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

    // Fetch the HITL approval request
    const hitlRequest = await db.hitlApprovalRequest.findUnique({
      where: { requestId },
    });

    if (!hitlRequest) {
      return NextResponse.json(
        { error: "Solicitud no encontrada" },
        { status: 404 }
      );
    }

    // Fetch decisions for this request
    const decisions = await db.hitlApprovalDecision.findMany({
      where: { requestId },
      orderBy: { decidedAt: "desc" },
    });

    // Parse action payload for evidence
    let payload: Record<string, unknown> = {};
    try {
      payload = JSON.parse(hitlRequest.actionPayload);
    } catch {
      // ignore
    }

    // Parse metadata for LLM verdict and evidence
    let metadata: Record<string, unknown> = {};
    try {
      metadata = JSON.parse(hitlRequest.metadata);
    } catch {
      // ignore
    }

    // Build evidence for and against
    const evidenceFor: Array<{ point: string; weight: number; source: string }> = [];
    const evidenceAgainst: Array<{ point: string; weight: number; source: string }> = [];

    // Add LLM verdict as evidence
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

    // Add policy check evidence
    if (hitlRequest.targetAction === "schema_drift") {
      evidenceFor.push({
        point: "El cambio detectado es consistente con patrones previos aprobados",
        weight: 0.5,
        source: "Memoria Adaptativa",
      });
    } else if (hitlRequest.targetAction === "intent_routing") {
      evidenceFor.push({
        point: "La ruta de intención sugerida tiene alta coincidencia semántica",
        weight: 0.6,
        source: "Enrutador de Intenciones",
      });
    }

    // Add priority-based evidence
    if (hitlRequest.priority === "low") {
      evidenceFor.push({
        point: "La solicitud tiene prioridad baja — impacto limitado",
        weight: 0.3,
        source: "Evaluador de Riesgo",
      });
    } else if (hitlRequest.priority === "high" || hitlRequest.priority === "critical") {
      evidenceAgainst.push({
        point: `La solicitud tiene prioridad ${hitlRequest.priority} — requiere atención especial`,
        weight: 0.6,
        source: "Evaluador de Riesgo",
      });
    }

    // Add reversibility evidence
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

    // Determine action category for color coding
    let actionCategory = "safe"; // grey
    if (
      hitlRequest.targetAction?.includes("financial") ||
      hitlRequest.targetAction?.includes("payment") ||
      hitlRequest.type === "data_access" && hitlRequest.targetResource?.includes("financial")
    ) {
      actionCategory = "financial"; // amber
    }
    if (
      hitlRequest.targetAction?.includes("delete") ||
      hitlRequest.targetAction?.includes("destructive") ||
      hitlRequest.priority === "critical"
    ) {
      actionCategory = "destructive"; // red
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
