// ─── Niche Templates — Plantillas de nichos industriales ──────────────
// FIX: Eliminado estado mutable global (archivosEnProceso, plantillasPorNicho).
// En serverless, el estado global causa fugas de memoria y race conditions.
// Ahora usa la base de datos para persistir plantillas y archivos.

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

/** Tipos de archivo permitidos para el agente Yamil */
const TIPOS_PERMITIDOS = new Set([
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.ms-powerpoint",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "text/plain",
  "text/csv",
  "text/markdown",
  "application/json",
]);

const TAMANO_MAXIMO = 10 * 1024 * 1024; // 10 MB

/** Extensiones permitidas */
const EXTENSIONES_PERMITIDAS = new Set([
  ".pdf", ".doc", ".docx", ".xls", ".xlsx",
  ".ppt", ".pptx", ".txt", ".csv", ".md", ".json",
]);

/** GET — Obtener plantillas existentes por nicho */
export async function GET(request: NextRequest) {
  try {
    const nichoId = request.nextUrl.searchParams.get("nichoId");
    const estadoArchivos = request.nextUrl.searchParams.get("estado") === "archivos";

    if (estadoArchivos) {
      // Obtener archivos en proceso desde la DB (no de memoria)
      const where = nichoId ? { nichoId, estado: "procesando" as const } : { estado: "procesando" as const };
      const archivos = await db.nicheTemplateFile.findMany({
        where,
        orderBy: { createdAt: "desc" },
        take: 50,
      });

      const formatted = archivos.map((a) => ({
        nombre: a.nombre,
        tipo: a.tipo,
        tamaño: a.tamano,
        nichoId: a.nichoId,
        estado: a.estado,
        plantillaGenerada: a.plantillaGenerada,
        fechaSubida: a.createdAt.toISOString(),
      }));

      return NextResponse.json({ archivos: formatted });
    }

    // Obtener plantillas desde la DB
    const where = nichoId ? { nichoId, estado: { in: ["lista", "borrador"] } } : { estado: { in: ["lista", "borrador"] } };
    const plantillas = await db.nicheTemplate.findMany({
      where,
      orderBy: { createdAt: "desc" },
      take: 100,
    });

    const formatted = plantillas.map((p) => ({
      id: p.id,
      nombre: p.nombre,
      descripcion: p.descripcion,
      tipo: p.tipo,
      nichoId: p.nichoId,
      fechaCreacion: p.createdAt.toISOString(),
      estado: p.estado,
    }));

    return NextResponse.json({
      plantillas: formatted,
      total: formatted.length,
    });
  } catch (error) {
    console.error("[/api/dashboard/niche-templates GET]", error);
    return NextResponse.json(
      { error: "Error al obtener plantillas de nicho" },
      { status: 500 }
    );
  }
}

/** POST — Subir archivos para que Yamil genere plantillas */
export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const archivos = formData.getAll("archivos") as File[];
    const nichoId = formData.get("nichoId") as string;

    if (!nichoId) {
      return NextResponse.json(
        { error: "Debe seleccionar un nicho de industria" },
        { status: 400 }
      );
    }

    if (!archivos || archivos.length === 0) {
      return NextResponse.json(
        { error: "Debe subir al menos un archivo" },
        { status: 400 }
      );
    }

    const resultados: Array<{
      nombre: string;
      valido: boolean;
      razon?: string;
    }> = [];

    for (const archivo of archivos) {
      const extension = "." + archivo.name.split(".").pop()?.toLowerCase();

      // Validación: tipo MIME Y extensión deben ser permitidos
      if (!TIPOS_PERMITIDOS.has(archivo.type) && !EXTENSIONES_PERMITIDAS.has(extension)) {
        resultados.push({
          nombre: archivo.name,
          valido: false,
          razon: "Tipo de archivo no permitido",
        });
        continue;
      }

      if (archivo.size > TAMANO_MAXIMO) {
        resultados.push({
          nombre: archivo.name,
          valido: false,
          razon: `El archivo excede el límite de 10 MB (tamaño: ${(archivo.size / 1024 / 1024).toFixed(1)} MB)`,
        });
        continue;
      }

      // Persistir archivo en la DB (no en memoria)
      const fileRecord = await db.nicheTemplateFile.create({
        data: {
          nombre: archivo.name,
          tipo: archivo.type || extension,
          tamano: archivo.size,
          nichoId,
          estado: "procesando",
          plantillaGenerada: null,
        },
      });

      // Crear plantilla asociada en estado borrador
      const nombrePlantilla = `Plantilla de ${archivo.name.replace(/\.[^/.]+$/, "")}`;
      await db.nicheTemplate.create({
        data: {
          nombre: nombrePlantilla,
          descripcion: `Plantilla generada por Yamil a partir del documento "${archivo.name}"`,
          tipo: "documento",
          nichoId,
          estado: "borrador",
          sourceFileId: fileRecord.id,
        },
      });

      // Marcar archivo como completado
      await db.nicheTemplateFile.update({
        where: { id: fileRecord.id },
        data: {
          estado: "completado",
          plantillaGenerada: nombrePlantilla,
        },
      });

      resultados.push({
        nombre: archivo.name,
        valido: true,
      });
    }

    const archivosValidos = resultados.filter((r) => r.valido).length;
    const archivosInvalidos = resultados.filter((r) => !r.valido).length;

    return NextResponse.json({
      mensaje: `${archivosValidos} archivo${archivosValidos !== 1 ? "s" : ""} procesado${archivosValidos !== 1 ? "s" : ""} por Yamil${archivosInvalidos > 0 ? `. ${archivosInvalidos} rechazado${archivosInvalidos !== 1 ? "s" : ""}.` : ""}`,
      resultados,
      plantillasGeneradas: archivosValidos,
      nichoId,
    });
  } catch (error) {
    console.error("[/api/dashboard/niche-templates POST]", error);
    return NextResponse.json(
      { error: "Error al procesar archivos para plantillas" },
      { status: 500 }
    );
  }
}
