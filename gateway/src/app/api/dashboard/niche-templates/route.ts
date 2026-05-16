import { NextRequest, NextResponse } from "next/server";

/** Tipos de archivo permitidos para el agente Yamil */
const TIPOS_PERMITIDOS = [
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
];

const TAMANO_MAXIMO = 10 * 1024 * 1024; // 10 MB

/** Extensiones permitidas */
const EXTENSIONES_PERMITIDAS = [
  ".pdf", ".doc", ".docx", ".xls", ".xlsx",
  ".ppt", ".pptx", ".txt", ".csv", ".md", ".json",
];

interface ArchivoSubido {
  nombre: string;
  tipo: string;
  tamaño: number;
  nichoId: string;
  estado: "recibido" | "procesando" | "completado" | "error";
  plantillaGenerada: string | null;
  fechaSubida: string;
}

/** Almacén temporal en memoria (simulado) */
const archivosEnProceso: ArchivoSubido[] = [];

/** Plantillas generadas por nicho (simulado) */
const plantillasPorNicho: Record<string, Array<{
  id: string;
  nombre: string;
  descripcion: string;
  tipo: string;
  nichoId: string;
  fechaCreacion: string;
  estado: "lista" | "borrador";
}>> = {
  healthtech: [
    {
      id: "tpl-h1",
      nombre: "Consentimiento Informado Digital",
      descripcion: "Plantilla de consentimiento informado para telemedicina, conforme HIPAA",
      tipo: "documento",
      nichoId: "healthtech",
      fechaCreacion: new Date().toISOString(),
      estado: "lista",
    },
    {
      id: "tpl-h2",
      nombre: "Registro de Auditoría de Acceso",
      descripcion: "Formato estándar para registrar accesos a historiales clínicos",
      tipo: "formulario",
      nichoId: "healthtech",
      fechaCreacion: new Date().toISOString(),
      estado: "lista",
    },
  ],
  fintech: [
    {
      id: "tpl-f1",
      nombre: "Aprobación de Transferencia Mayor",
      descripcion: "Flujo de aprobación humana para transferencias superiores a $10,000",
      tipo: "flujo",
      nichoId: "fintech",
      fechaCreacion: new Date().toISOString(),
      estado: "lista",
    },
    {
      id: "tpl-f2",
      nombre: "Registro Inmutable de Transacciones",
      descripcion: "Formato de registro conforme PCI-DSS para auditoría financiera",
      tipo: "registro",
      nichoId: "fintech",
      fechaCreacion: new Date().toISOString(),
      estado: "borrador",
    },
  ],
  edtech: [
    {
      id: "tpl-e1",
      nombre: "Consentimiento Parental Verificado",
      descripcion: "Plantilla COPPA para verificación de consentimiento parental",
      tipo: "formulario",
      nichoId: "edtech",
      fechaCreacion: new Date().toISOString(),
      estado: "lista",
    },
  ],
  legaltech: [
    {
      id: "tpl-l1",
      nombre: "Protección de Privilegio Abogado-Cliente",
      descripcion: "Plantilla de clasificación y protección documental conforme ABA/GDPR",
      tipo: "documento",
      nichoId: "legaltech",
      fechaCreacion: new Date().toISOString(),
      estado: "lista",
    },
  ],
  manufacturing: [
    {
      id: "tpl-m1",
      nombre: "Validación de Cambios Críticos",
      descripcion: "Flujo de aprobación para modificaciones en líneas de producción",
      tipo: "flujo",
      nichoId: "manufacturing",
      fechaCreacion: new Date().toISOString(),
      estado: "borrador",
    },
  ],
  government: [
    {
      id: "tpl-g1",
      nombre: "Cadena de Custodia Digital",
      descripcion: "Formato NIST/FISMA para trazabilidad de datos sensibles gubernamentales",
      tipo: "registro",
      nichoId: "government",
      fechaCreacion: new Date().toISOString(),
      estado: "lista",
    },
  ],
};

/** GET — Obtener plantillas existentes por nicho */
export async function GET(request: NextRequest) {
  try {
    const nichoId = request.nextUrl.searchParams.get("nichoId");
    const estadoArchivos = request.nextUrl.searchParams.get("estado") === "archivos";

    if (estadoArchivos) {
      // Devolver archivos en proceso
      const archivosFiltrados = nichoId
        ? archivosEnProceso.filter((a) => a.nichoId === nichoId)
        : archivosEnProceso;
      return NextResponse.json({ archivos: archivosFiltrados });
    }

    // Devolver plantillas generadas
    if (nichoId && plantillasPorNicho[nichoId]) {
      return NextResponse.json({
        plantillas: plantillasPorNicho[nichoId],
        total: plantillasPorNicho[nichoId].length,
      });
    }

    // Devolver todas las plantillas
    const todasLasPlantillas = Object.values(plantillasPorNicho).flat();
    return NextResponse.json({
      plantillas: todasLasPlantillas,
      total: todasLasPlantillas.length,
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

      if (!TIPOS_PERMITIDOS.includes(archivo.type) && !EXTENSIONES_PERMITIDAS.includes(extension)) {
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

      // Simular procesamiento por Yamil
      const nuevoArchivo: ArchivoSubido = {
        nombre: archivo.name,
        tipo: archivo.type || extension,
        tamaño: archivo.size,
        nichoId,
        estado: "procesando",
        plantillaGenerada: null,
        fechaSubida: new Date().toISOString(),
      };

      archivosEnProceso.push(nuevoArchivo);

      // Simular que Yamil genera la plantilla después de procesar
      const nombrePlantilla = `Plantilla de ${archivo.name.replace(/\.[^/.]+$/, "")}`;
      if (!plantillasPorNicho[nichoId]) {
        plantillasPorNicho[nichoId] = [];
      }

      plantillasPorNicho[nichoId].push({
        id: `tpl-${nichoId}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        nombre: nombrePlantilla,
        descripcion: `Plantilla generada por Yamil a partir del documento "${archivo.name}"`,
        tipo: "documento",
        nichoId,
        fechaCreacion: new Date().toISOString(),
        estado: "borrador",
      });

      nuevoArchivo.estado = "completado";
      nuevoArchivo.plantillaGenerada = nombrePlantilla;

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
