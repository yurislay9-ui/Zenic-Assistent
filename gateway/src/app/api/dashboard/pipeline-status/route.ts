import { NextResponse } from "next/server";
import { db } from "@/lib/db";

export async function GET() {
  try {
    const now = new Date();
    const last1h = new Date(now.getTime() - 60 * 60 * 1000);

    // Get recent tool executions to determine pipeline activity
    const recentExecutions = await db.toolExecution.findMany({
      where: { createdAt: { gte: last1h } },
      select: { status: true, verdict: true, createdAt: true },
      orderBy: { createdAt: "desc" },
      take: 50,
    });

    // Compute pipeline step statuses based on real execution data
    const total = recentExecutions.length;
    const active = total > 0;

    // 9 steps of the deterministic pipeline
    const steps = [
      {
        id: 1,
        name: "Búsqueda en Memoria",
        description: "Consulta la base de conocimiento adaptativa",
        status: active ? "active" : "idle",
        throughput: total,
      },
      {
        id: 2,
        name: "Clasificación de Intención",
        description: "Identifica qué quiere hacer el usuario",
        status: active ? "active" : "idle",
        throughput: total,
      },
      {
        id: 3,
        name: "Extracción de Entidades",
        description: "Aisla los datos clave de la solicitud",
        status: active ? "active" : "idle",
        throughput: total,
      },
      {
        id: 4,
        name: "Validación de Esquema",
        description: "Verifica que los datos cumplan el formato esperado",
        status: active ? "active" : "idle",
        throughput: total,
      },
      {
        id: 5,
        name: "Adaptación del Flujo",
        description: "Ajusta parámetros sin alterar la estructura",
        status: active ? "active" : "idle",
        throughput: total,
      },
      {
        id: 6,
        name: "Verificación de Permisos",
        description: "Confirma que el usuario tiene autorización",
        status: active ? "active" : "idle",
        throughput: total,
      },
      {
        id: 7,
        name: "Recolección de Contexto",
        description: "Junta toda la evidencia disponible",
        status: active ? "active" : "idle",
        throughput: total,
      },
      {
        id: 8,
        name: "Enrutamiento de Herramienta",
        description: "Dirige la solicitud al servicio correcto",
        status: active ? "active" : "idle",
        throughput: total,
      },
      {
        id: 9,
        name: "Simulación en Seco",
        description: "Ejecuta la acción en modo prueba antes de aprobar",
        status: active ? "active" : "idle",
        throughput: total,
      },
    ];

    // Determine which step is currently "highlighted" based on time
    const secondsInCycle = 90; // Each full pipeline cycle ~90s
    const cyclePosition = (now.getTime() / 1000) % secondsInCycle;
    const currentStep = Math.floor((cyclePosition / secondsInCycle) * 9) + 1;

    // Mark the current step
    steps.forEach((step) => {
      if (step.id === currentStep && active) {
        step.status = "processing";
      }
    });

    const completed = recentExecutions.filter(
      (e) => e.status === "completed"
    ).length;
    const denied = recentExecutions.filter(
      (e) => e.verdict === "deny"
    ).length;

    return NextResponse.json({
      steps,
      currentStep,
      isActive: active,
      totalProcessed: total,
      completedCount: completed,
      deniedCount: denied,
      cycleTime: secondsInCycle,
    });
  } catch (error) {
    console.error("[/api/dashboard/pipeline-status GET]", error);
    return NextResponse.json(
      { error: "Error al obtener estado del pipeline" },
      { status: 500 }
    );
  }
}
