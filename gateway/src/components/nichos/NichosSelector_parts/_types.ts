export interface NichoIndustrial {
  id: string;
  nombre: string;
  icono: string;
  emoji: string;
  standard: string;
  standardNombre: string;
  standardDescripcion: string;
  reglas: string[];
  denyAbsolutos: string[];
  color: string;
  categoria: "salud" | "financiero" | "educacion" | "legal" | "industrial" | "publico" | "comercio" | "tecnologia" | "servicios";
}

/** Plantilla generada por Yamil */
export interface PlantillaNicho {
  id: string;
  nombre: string;
  descripcion: string;
  tipo: string;
  nichoId: string;
  fechaCreacion: string;
  estado: "lista" | "borrador";
}

/** Archivo subido para procesamiento */
export interface ArchivoSubido {
  nombre: string;
  tipo: string;
  tamaño: number;
  nichoId: string;
  estado: "recibido" | "procesando" | "completado" | "error";
  plantillaGenerada: string | null;
  fechaSubida: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// DATOS DE LOS 24 NICHOS INDUSTRIALES
// ═══════════════════════════════════════════════════════════════════════════════

