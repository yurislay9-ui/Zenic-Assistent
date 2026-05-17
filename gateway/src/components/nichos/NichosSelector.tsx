"use client";

import { useState, useMemo, useCallback, useRef, useEffect } from "react";
import {
  Heart,
  Landmark,
  GraduationCap,
  Scale,
  Factory,
  Building2,
  Stethoscope,
  Pill,
  Microscope,
  ShieldCheck,
  Truck,
  ShoppingCart,
  Megaphone,
  Plane,
  TreePine,
  Zap,
  Waves,
  Cpu,
  Smartphone,
  Workflow,
  Lock,
  CheckCircle2,
  Upload,
  FileText,
  FileUp,
  FileCheck,
  Sparkles,
  FolderOpen,
  RefreshCw,
  XCircle,
  AlertTriangle,
  Clock,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

// ═══════════════════════════════════════════════════════════════════════════════
// TIPOS ESTRICTOS
// ═══════════════════════════════════════════════════════════════════════════════

/** Metadatos extendidos de un nicho industrial */
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

export const NICHOS_INDUSTRIALES: NichoIndustrial[] = [
  // ─── SALUD ──────────────────────────────────────────────────────
  {
    id: "healthtech",
    nombre: "Telemedicina y Salud",
    icono: "Heart",
    emoji: "💚",
    standard: "HIPAA",
    standardNombre: "Health Insurance Portability and Accountability Act",
    standardDescripcion: "Protección de datos de pacientes y registros médicos electrónicos en entornos de telemedicina",
    reglas: [
      "Cifrado obligatorio de datos de pacientes (en tránsito y en reposo)",
      "Auditoría de acceso a historiales clínicos con trazabilidad",
      "Consentimiento informado digital requerido antes de cualquier acción",
      "Separación de datos clínicos y administrativos",
      "Retención mínima de 6 años de registros de acceso",
    ],
    denyAbsolutos: [
      "La IA nunca puede modificar recetas médicas directamente",
      "La IA nunca puede diagnosticar sin validación humana",
      "La IA nunca puede acceder a datos de pacientes sin autorización explícita",
    ],
    color: "emerald",
    categoria: "salud",
  },
  {
    id: "pharma",
    nombre: "Farmacéutica",
    icono: "Pill",
    emoji: "💊",
    standard: "FDA 21 CFR Part 11 / GxP",
    standardNombre: "Code of Federal Regulations Title 21 — Electronic Records & Signatures",
    standardDescripcion: "Regulación de registros electrónicos y firmas digitales en la industria farmacéutica",
    reglas: [
      "Trazabilidad completa de cada lote de producción",
      "Firmas electrónicas con integridad garantizada",
      "Validación de sistemas computarizados según GAMP5",
      "Control de cambios documentado y aprobado",
    ],
    denyAbsolutos: [
      "La IA nunca puede aprobar liberación de lotes sin firma humana",
      "La IA nunca puede alterar datos de ensayos clínicos",
    ],
    color: "teal",
    categoria: "salud",
  },
  {
    id: "biotech",
    nombre: "Biotecnología",
    icono: "Microscope",
    emoji: "🔬",
    standard: "ISO 13485 / GLP",
    standardNombre: "Gestiónd de Calidad en Dispositivos Médicos / Buenas Prácticas de Laboratorio",
    standardDescripcion: "Calidad y seguridad en investigación biotecnológica y desarrollo de dispositivos médicos",
    reglas: [
      "Registro inmutable de experimentos y resultados",
      "Control de acceso basado en roles para datos de investigación",
      "Auditoría de modificaciones en protocolos experimentales",
    ],
    denyAbsolutos: [
      "La IA nunca puede fabricar resultados de investigación",
      "La IA nunca puede autorizar uso de material biológico sin aprobación",
    ],
    color: "lime",
    categoria: "salud",
  },
  {
    id: "health_insur",
    nombre: "Seguros de Salud",
    icono: "Stethoscope",
    emoji: "🩺",
    standard: "HIPAA / ACA",
    standardNombre: "Affordable Care Act — Regulaciones de Seguros de Salud",
    standardDescripcion: "Protección de datos de pacientes y cumplimiento en procesamiento de reclamos de salud",
    reglas: [
      "Verificación de elegibilidad antes de procesar reclamos",
      "Cifrado de información médica en todas las transacciones",
      "Auditoría de acceso a registros de pacientes asegurados",
    ],
    denyAbsolutos: [
      "La IA nunca puede denegar cobertura médica de forma autónoma",
      "La IA nunca puede acceder a historiales médicos sin autorización HIPAA",
    ],
    color: "green",
    categoria: "salud",
  },

  // ─── FINANCIERO ─────────────────────────────────────────────────
  {
    id: "fintech",
    nombre: "Fintech y Pagos",
    icono: "Landmark",
    emoji: "🏦",
    standard: "PCI-DSS / AML/KYC",
    standardNombre: "Payment Card Industry Data Security Standard / Anti-Money Laundering",
    standardDescripcion: "Seguridad de datos de tarjetas y prevención de lavado de dinero en servicios financieros",
    reglas: [
      "Tokenización obligatoria de datos de tarjetas",
      "Registro inmutable de todas las transacciones",
      "Aprobación humana para transferencias mayores a $10,000",
      "Verificación de identidad KYC antes de apertura de cuentas",
    ],
    denyAbsolutos: [
      "La IA nunca puede ejecutar transferencias > $10,000 sin aprobación humana",
      "La IA nunca puede alterar registros de transacciones",
      "La IA nunca puede omitir verificaciones KYC/AML",
    ],
    color: "amber",
    categoria: "financiero",
  },
  {
    id: "banking",
    nombre: "Banca Digital",
    icono: "Landmark",
    emoji: "🏛️",
    standard: "Basel III / SOX",
    standardNombre: "Acuerdos de Basilea III / Sarbanes-Oxley Act",
    standardDescripcion: "Regulación de capital, liquidez y reportes financieros en banca digital",
    reglas: [
      "Reportes regulatorios automatizados con trazabilidad",
      "Control de acceso multinivel a sistemas centrales",
      "Conciliación automática con validación humana",
    ],
    denyAbsolutos: [
      "La IA nunca puede modificar balances contables sin auditoría",
      "La IA nunca puede generar reportes regulatorios falsos",
    ],
    color: "yellow",
    categoria: "financiero",
  },
  {
    id: "insurance",
    nombre: "Seguros",
    icono: "ShieldCheck",
    emoji: "🛡️",
    standard: "Solvency II / NAIC",
    standardNombre: "Directiva de Solvencia II / National Association of Insurance Commissioners",
    standardDescripcion: "Requisitos de capital y gobernanza para compañías de seguros",
    reglas: [
      "Cálculo de reservas con auditoría automática",
      "Registro de pólizas y siniestros con cadena inmutable",
      "Validación humana para siniestros mayores al umbral",
    ],
    denyAbsolutos: [
      "La IA nunca puede aprobar siniestros de alto valor sin revisión humana",
      "La IA nunca puede modificar términos de pólizas vigentes",
    ],
    color: "orange",
    categoria: "financiero",
  },
  {
    id: "crypto",
    nombre: "Criptoactivos y DeFi",
    icono: "Waves",
    emoji: "₿",
    standard: "MiCA / FATF Travel Rule",
    standardNombre: "Markets in Crypto-Assets / Financial Action Task Force",
    standardDescripcion: "Regulación de criptoactivos y prevención de lavado de dinero en finanzas descentralizadas",
    reglas: [
      "Verificación de contraparte en cada transacción",
      "Registro inmutable de operaciones on-chain/off-chain",
      "Monitoreo de patrones de lavado de dinero",
    ],
    denyAbsolutos: [
      "La IA nunca puede ejecutar transacciones de mezcla (mixing) de fondos",
      "La IA nunca puede eludir controles de Travel Rule",
    ],
    color: "purple",
    categoria: "financiero",
  },

  // ─── EDUCACIÓN ──────────────────────────────────────────────────
  {
    id: "edtech",
    nombre: "Tecnología Educativa",
    icono: "GraduationCap",
    emoji: "🎓",
    standard: "COPPA / FERPA",
    standardNombre: "Children's Online Privacy Protection Act / Family Educational Rights and Privacy Act",
    standardDescripcion: "Protección de datos de menores y registros estudiantiles en plataformas educativas",
    reglas: [
      "Protección de datos de menores de 13 años",
      "Consentimiento parental verificado para menores",
      "Anonimización de registros estudiantiles en análisis",
      "Derecho a eliminación de datos personales",
    ],
    denyAbsolutos: [
      "La IA nunca puede generar calificaciones sin intervención docente",
      "La IA nunca puede recopilar datos de menores sin consentimiento parental",
    ],
    color: "blue",
    categoria: "educacion",
  },
  {
    id: "highered",
    nombre: "Educación Superior",
    icono: "GraduationCap",
    emoji: "📚",
    standard: "FERPA / GDPR",
    standardNombre: "Family Educational Rights and Privacy Act / General Data Protection Regulation",
    standardDescripcion: "Protección de datos académicos e investigación en instituciones de educación superior",
    reglas: [
      "Control de acceso granular a expedientes académicos",
      "Auditoría de acceso a datos de investigación",
      "Consentimiento informado para uso de datos en investigación",
    ],
    denyAbsolutos: [
      "La IA nunca puede alterar expedientes académicos",
      "La IA nunca puede usar datos de investigación sin consentimiento",
    ],
    color: "sky",
    categoria: "educacion",
  },
  {
    id: "corptraining",
    nombre: "Capacitación Corporativa",
    icono: "Workflow",
    emoji: "📋",
    standard: "SCORM / ISO 10015",
    standardNombre: "Sharable Content Object Reference Model / Gestión de Calidad en Capacitación",
    standardDescripcion: "Estándares de contenido educativo y gestión de calidad en capacitación empresarial",
    reglas: [
      "Registro inmutable de certificaciones obtenidas",
      "Trazabilidad de cumplimiento de programas de capacitación",
      "Validación de competencias con evidencia documentada",
    ],
    denyAbsolutos: [
      "La IA nunca puede certificar competencias sin evaluación humana",
      "La IA nunca puede falsificar registros de capacitación",
    ],
    color: "indigo",
    categoria: "educacion",
  },

  // ─── LEGAL ──────────────────────────────────────────────────────
  {
    id: "legaltech",
    nombre: "Tecnología Legal",
    icono: "Scale",
    emoji: "⚖️",
    standard: "ABA / GDPR",
    standardNombre: "American Bar Association / General Data Protection Regulation",
    standardDescripcion: "Protección del privilegio abogado-cliente y datos personales en tecnología legal",
    reglas: [
      "Privilegio abogado-cliente protegido por diseño",
      "Retención documental por jurisdicción",
      "No generación de opiniones legales por IA",
      "Cadena de custodia digital para evidencia",
    ],
    denyAbsolutos: [
      "La IA nunca puede generar opiniones legales vinculantes",
      "La IA nunca puede revelar comunicaciones privilegiadas",
      "La IA nunca puede alterar documentos legales sin bitácora",
    ],
    color: "rose",
    categoria: "legal",
  },
  {
    id: "compliance",
    nombre: "Cumplimiento Regulatorio",
    icono: "ShieldCheck",
    emoji: "📜",
    standard: "SOX / ISO 37301",
    standardNombre: "Sarbanes-Oxley Act / Compliance Management Systems",
    standardDescripcion: "Sistemas de gestión de cumplimiento y reportes regulatorios corporativos",
    reglas: [
      "Reportes de cumplimiento con firma digital inmutable",
      "Mapeo de regulaciones a controles internos",
      "Auditoría continua de desviaciones regulatorias",
    ],
    denyAbsolutos: [
      "La IA nunca puede ocultar violaciones regulatorias",
      "La IA nunca puede alterar reportes de cumplimiento",
    ],
    color: "pink",
    categoria: "legal",
  },
  {
    id: "ip",
    nombre: "Propiedad Intelectual",
    icono: "Lock",
    emoji: "🔒",
    standard: "WIPO / TRIPS",
    standardNombre: "World Intellectual Property Organization / Trade-Related Aspects of IP Rights",
    standardDescripcion: "Protección y gestión de patentes, marcas y derechos de autor",
    reglas: [
      "Registro de creación con sello temporal inmutable",
      "Control de acceso a documentos de patentes pendientes",
      "Auditoría de uso de propiedad intelectual",
    ],
    denyAbsolutos: [
      "La IA nunca puede plagiar contenido protegido",
      "La IA nunca puede revelar secretos comerciales",
    ],
    color: "fuchsia",
    categoria: "legal",
  },

  // ─── INDUSTRIAL ─────────────────────────────────────────────────
  {
    id: "manufacturing",
    nombre: "Manufactura Inteligente",
    icono: "Factory",
    emoji: "🏭",
    standard: "ISO 27001",
    standardNombre: "International Standard for Information Security Management",
    standardDescripcion: "Gestión de seguridad de la información en entornos de manufactura inteligente",
    reglas: [
      "Control de acceso a sistemas SCADA",
      "Registro de modificaciones en líneas de producción",
      "Validación humana para cambios críticos en procesos",
      "Monitoreo de integridad de sensores IoT",
    ],
    denyAbsolutos: [
      "La IA nunca puede modificar parámetros de seguridad de planta sin autorización",
      "La IA nunca puede desactivar sistemas de alarma industrial",
    ],
    color: "slate",
    categoria: "industrial",
  },
  {
    id: "supplychain",
    nombre: "Cadena de Suministro",
    icono: "Truck",
    emoji: "🚛",
    standard: "ISO 28000 / C-TPAT",
    standardNombre: "Supply Chain Security Management / Customs-Trade Partnership Against Terrorism",
    standardDescripcion: "Seguridad y trazabilidad en cadenas de suministro globales",
    reglas: [
      "Trazabilidad end-to-end de productos y materiales",
      "Validación de proveedores con verificación automática",
      "Registro inmutable de movimiento de mercancías",
    ],
    denyAbsolutos: [
      "La IA nunca puede alterar registros de trazabilidad",
      "La IA nunca puede autorizar ingreso de mercancías sin verificación",
    ],
    color: "stone",
    categoria: "industrial",
  },
  {
    id: "energy",
    nombre: "Energía y Utilities",
    icono: "Zap",
    emoji: "⚡",
    standard: "NERC CIP / IEC 62351",
    standardNombre: "Critical Infrastructure Protection / Power Systems Security",
    standardDescripcion: "Protección de infraestructura crítica en sector energético",
    reglas: [
      "Monitoreo de ciberseguridad en infraestructura crítica",
      "Validación humana para despacho de carga",
      "Auditoría de acceso a sistemas de control de red",
    ],
    denyAbsolutos: [
      "La IA nunca puede despachar carga eléctrica sin autorización humana",
      "La IA nunca puede desactivar protecciones de red eléctrica",
    ],
    color: "yellow",
    categoria: "industrial",
  },
  {
    id: "mining",
    nombre: "Minería y Recursos",
    icono: "TreePine",
    emoji: "⛏️",
    standard: "ISO 14001 / IFC Performance Standards",
    standardNombre: "Environmental Management / International Finance Corporation Standards",
    standardDescripcion: "Gestión ambiental y responsabilidad social en minería y recursos naturales",
    reglas: [
      "Monitoreo de impacto ambiental con registros inmutables",
      "Auditoría de cumplimiento de permisos ambientales",
      "Validación de seguridad en operaciones de alta riesgo",
    ],
    denyAbsolutos: [
      "La IA nunca puede autorizar operaciones sin permisos vigentes",
      "La IA nunca puede ocultar violaciones ambientales",
    ],
    color: "amber",
    categoria: "industrial",
  },

  // ─── PÚBLICO ───────────────────────────────────────────────────
  {
    id: "government",
    nombre: "Gobierno y Sector Público",
    icono: "Building2",
    emoji: "🏛️",
    standard: "NIST / FISMA",
    standardNombre: "National Institute of Standards and Technology / Federal Information Security Modernization Act",
    standardDescripcion: "Clasificación y protección de datos sensibles gubernamentales",
    reglas: [
      "Clasificación obligatoria de datos sensibles",
      "Cadena de custodia digital inmutable",
      "Aprobación multinivel para acceso a datos clasificados",
      "Auditoría de todas las acciones sobre datos gubernamentales",
    ],
    denyAbsolutos: [
      "La IA nunca puede desclasificar información sin autorización",
      "La IA nunca puede acceder a datos de seguridad nacional sin clearance",
      "La IA nunca puede alterar registros oficiales del estado",
    ],
    color: "blue",
    categoria: "publico",
  },
  {
    id: "defense",
    nombre: "Defensa y Seguridad Nacional",
    icono: "ShieldCheck",
    emoji: "🎖️",
    standard: "ITAR / CMMC",
    standardNombre: "International Traffic in Arms Regulations / Cybersecurity Maturity Model Certification",
    standardDescripcion: "Control de exportaciones de defensa y ciberseguridad en contratos militares",
    reglas: [
      "Control de acceso basado en clearance de seguridad",
      "Auditoría de todas las transacciones con datos controlados",
      "Aislamiento de redes con datos clasificados",
    ],
    denyAbsolutos: [
      "La IA nunca puede transferir datos controlados a sistemas no autorizados",
      "La IA nunca puede clasificar o desclasificar información militar",
    ],
    color: "red",
    categoria: "publico",
  },
  {
    id: "critical_infra",
    nombre: "Infraestructura Crítica",
    icono: "Building2",
    emoji: "🏗️",
    standard: "NIST CSF / EU NIS2",
    standardNombre: "Cybersecurity Framework / Network and Information Security Directive 2",
    standardDescripcion: "Protección de infraestructura crítica y servicios esenciales",
    reglas: [
      "Detección de anomalias en tiempo real",
      "Planes de respuesta a incidentes con validación humana",
      "Respaldo y recuperación con verificación de integridad",
    ],
    denyAbsolutos: [
      "La IA nunca puede desactivar sistemas de protección de infraestructura crítica",
      "La IA nunca puede aislar servicios esenciales sin autorización",
    ],
    color: "gray",
    categoria: "publico",
  },

  // ─── COMERCIO ──────────────────────────────────────────────────
  {
    id: "ecommerce",
    nombre: "Comercio Electrónico",
    icono: "ShoppingCart",
    emoji: "🛒",
    standard: "PCI-DSS / PSD2",
    standardNombre: "Payment Card Industry Data Security Standard / Payment Services Directive 2",
    standardDescripcion: "Seguridad de pagos y protección al consumidor en comercio electrónico",
    reglas: [
      "Tokenización de datos de pago",
      "Autenticación fuerte del cliente (SCA)",
      "Protección contra fraude con monitoreo en tiempo real",
    ],
    denyAbsolutos: [
      "La IA nunca puede procesar pagos sin autenticación del cliente",
      "La IA nunca puede almacenar números de tarjeta sin tokenizar",
    ],
    color: "violet",
    categoria: "comercio",
  },
  {
    id: "retail",
    nombre: "Retail y Consumo",
    icono: "ShoppingCart",
    emoji: "🛍️",
    standard: "GDPR / CCPA",
    standardNombre: "General Data Protection Regulation / California Consumer Privacy Act",
    standardDescripcion: "Protección de datos de consumidores y personalización responsable",
    reglas: [
      "Consentimiento explícito para personalización",
      "Derecho de eliminación de datos personales",
      "Transparencia en uso de datos para recomendaciones",
    ],
    denyAbsolutos: [
      "La IA nunca puede usar datos de menores para publicidad dirigida",
      "La IA nunca puede discriminar precios sin transparencia",
    ],
    color: "cyan",
    categoria: "comercio",
  },
  {
    id: "realestate",
    nombre: "Bienes Raíces",
    icono: "Building2",
    emoji: "🏠",
    standard: "TRID / AML",
    standardNombre: "TILA-RESPA Integrated Disclosure / Anti-Money Laundering",
    standardDescripcion: "Transparencia en transacciones inmobiliarias y prevención de lavado de dinero",
    reglas: [
      "Divulgación obligatoria de términos de préstamos",
      "Verificación de identidad en transacciones de alto valor",
      "Registro de transacciones con trazabilidad completa",
    ],
    denyAbsolutos: [
      "La IA nunca puede aprobar transacciones inmobiliarias sin validación humana",
      "La IA nunca puede alterar documentos de propiedad",
    ],
    color: "emerald",
    categoria: "comercio",
  },

  // ─── TECNOLOGÍA ────────────────────────────────────────────────
  {
    id: "saas",
    nombre: "SaaS y Cloud",
    icono: "Cpu",
    emoji: "☁️",
    standard: "SOC 2 / ISO 27001",
    standardNombre: "Service Organization Control 2 / Information Security Management",
    standardDescripcion: "Controles de seguridad, disponibilidad y confidencialidad en servicios cloud",
    reglas: [
      "Cifrado de datos en reposo y en tránsito",
      "Control de acceso basado en roles (RBAC)",
      "Auditoría de acceso con registros inmutables",
    ],
    denyAbsolutos: [
      "La IA nunca puede acceder a datos de otros tenants",
      "La IA nunca puede desactivar controles de seguridad sin aprobación",
    ],
    color: "blue",
    categoria: "tecnologia",
  },
  {
    id: "iot",
    nombre: "IoT y Dispositivos",
    icono: "Smartphone",
    emoji: "📡",
    standard: "ETSI EN 303 645 / NIST 8259A",
    standardNombre: "Cybersecurity Standard for Consumer IoT / IoT Baseline Security",
    standardDescripcion: "Seguridad base para dispositivos IoT de consumo e industriales",
    reglas: [
      "Autenticación obligatoria en dispositivos IoT",
      "Actualizaciones de seguridad verificadas",
      "Cifrado de comunicaciones entre dispositivos y gateway",
    ],
    denyAbsolutos: [
      "La IA nunca puede desactivar actualizaciones de seguridad de dispositivos",
      "La IA nunca puede acceder a dispositivos sin autenticación",
    ],
    color: "teal",
    categoria: "tecnologia",
  },

  // ─── SERVICIOS ─────────────────────────────────────────────────
  {
    id: "travel",
    nombre: "Viajes y Hotelería",
    icono: "Plane",
    emoji: "✈️",
    standard: "PCI-DSS / GDPR",
    standardNombre: "Payment Card Industry Data Security Standard / General Data Protection Regulation",
    standardDescripcion: "Protección de datos de viajeros y seguridad de pagos en la industria de viajes",
    reglas: [
      "Cifrado de datos de pasaporte y documentos de viaje",
      "Consentimiento explícito para personalización de ofertas",
      "Registro de acceso a datos de huéspedes",
    ],
    denyAbsolutos: [
      "La IA nunca puede compartir datos de ubicación sin consentimiento",
      "La IA nunca puede procesar reservas sin confirmación del cliente",
    ],
    color: "sky",
    categoria: "servicios",
  },
  {
    id: "media",
    nombre: "Medios y Publicidad",
    icono: "Megaphone",
    emoji: "📢",
    standard: "GDPR / DSA",
    standardNombre: "General Data Protection Regulation / Digital Services Act",
    standardDescripcion: "Protección de datos y transparencia en medios digitales y publicidad programática",
    reglas: [
      "Consentimiento para tracking y publicidad personalizada",
      "Transparencia en algoritmos de recomendación",
      "Derecho de acceso y eliminación de datos de usuario",
    ],
    denyAbsolutos: [
      "La IA nunca puede generar contenido engañoso (deepfakes)",
      "La IA nunca puede segmentar audiencias con datos sensibles sin consentimiento",
    ],
    color: "pink",
    categoria: "servicios",
  },
];

// ═══════════════════════════════════════════════════════════════════════════════
// MAPEO DE ICONOS
// ═══════════════════════════════════════════════════════════════════════════════

const ICONO_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  Heart,
  Landmark,
  GraduationCap,
  Scale,
  Factory,
  Building2,
  Pill,
  Microscope,
  Stethoscope,
  ShieldCheck,
  Truck,
  ShoppingCart,
  Megaphone,
  Plane,
  Zap,
  Cpu,
  Smartphone,
  Workflow,
  Lock,
  Waves,
  TreePine,
};

/** Renderiza el icono de un nicho por su nombre — lazy, sin crear elementos al nivel del módulo */
function getIcono(nombre: string, className = "h-4 w-4") {
  const Icon = ICONO_MAP[nombre];
  return Icon ? <Icon className={className} /> : null;
}

// Colores por categoría para los badges de categoría
const COLOR_CATEGORIA: Record<string, { bg: string; text: string }> = {
  salud: { bg: "bg-emerald-100", text: "text-emerald-700" },
  financiero: { bg: "bg-amber-100", text: "text-amber-700" },
  educacion: { bg: "bg-blue-100", text: "text-blue-700" },
  legal: { bg: "bg-rose-100", text: "text-rose-700" },
  industrial: { bg: "bg-slate-100", text: "text-slate-700" },
  publico: { bg: "bg-gray-100", text: "text-gray-700" },
  comercio: { bg: "bg-violet-100", text: "text-violet-700" },
  tecnologia: { bg: "bg-cyan-100", text: "text-cyan-700" },
  servicios: { bg: "bg-pink-100", text: "text-pink-700" },
};

const ETIQUETA_CATEGORIA: Record<string, string> = {
  salud: "Salud",
  financiero: "Financiero",
  educacion: "Educación",
  legal: "Legal",
  industrial: "Industrial",
  publico: "Sector Público",
  comercio: "Comercio",
  tecnologia: "Tecnología",
  servicios: "Servicios",
};

// ═══════════════════════════════════════════════════════════════════════════════
// UTILIDADES
// ═══════════════════════════════════════════════════════════════════════════════

function tiempoRelativo(fechaStr: string): string {
  const d = new Date(fechaStr);
  const ahora = new Date();
  const diff = Math.floor((ahora.getTime() - d.getTime()) / 1000);
  if (diff < 60) return `hace ${diff}s`;
  if (diff < 3600) return `hace ${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `hace ${Math.floor(diff / 3600)}h`;
  return `hace ${Math.floor(diff / 86400)}d`;
}

function formatoTamañoArchivo(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ═══════════════════════════════════════════════════════════════════════════════
// PROPS DEL COMPONENTE
// ═══════════════════════════════════════════════════════════════════════════════

interface NichosSelectorProps {
  /** Nichos obtenidos del API (se usan los NICHOS_INDUSTRIALES locales como fuente completa) */
  nichosApi?: Array<{
    id: string;
    name: string;
    icon: string;
    standard: string;
    standardName: string;
    active: boolean;
    rules: string[];
  }>;
  /** Plantillas obtenidas del API */
  plantillas: PlantillaNicho[];
  /** Archivos subidos */
  archivosSubidos: ArchivoSubido[];
  /** Callback cuando se selecciona un nicho */
  onSeleccionarNicho: (nichoId: string) => void;
  /** Callback para subir archivos */
  onSubirArchivos: (archivos: FileList | File[]) => void;
  /** Si está subiendo archivos */
  subiendoArchivos: boolean;
  /** Si está cargando plantillas */
  cargandoPlantillas: boolean;
  /** ID del nicho seleccionado actualmente */
  nichoSeleccionado: string | null;
}

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENTE PRINCIPAL
// ═══════════════════════════════════════════════════════════════════════════════

export default function NichosSelector({
  plantillas,
  archivosSubidos,
  onSeleccionarNicho,
  onSubirArchivos,
  subiendoArchivos,
  cargandoPlantillas,
  nichoSeleccionado,
}: NichosSelectorProps) {
  // ─── Estado ────────────────────────────────────────────────────
  const [animacionActiva, setAnimacionActiva] = useState(false);
  const [dragActivo, setDragActivo] = useState(false);
  const inputArchivosRef = useRef<HTMLInputElement>(null);
  const tabScrollRef = useRef<HTMLDivElement>(null);

  // ─── Nicho actual ─────────────────────────────────────────────
  const nichoActual = useMemo(
    () => NICHOS_INDUSTRIALES.find((n) => n.id === nichoSeleccionado) ?? null,
    [nichoSeleccionado]
  );

  // ─── Animación al cambiar de nicho ────────────────────────────
  const manejarSeleccion = useCallback(
    (nichoId: string) => {
      setAnimacionActiva(false);
      requestAnimationFrame(() => {
        onSeleccionarNicho(nichoId);
        setAnimacionActiva(true);
      });
    },
    [onSeleccionarNicho]
  );

  // ─── Drag & Drop ──────────────────────────────────────────────
  const manejarDragOver = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (nichoSeleccionado) setDragActivo(true);
    },
    [nichoSeleccionado]
  );

  const manejarDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActivo(false);
  }, []);

  const manejarDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setDragActivo(false);
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0 && nichoSeleccionado) {
        onSubirArchivos(e.dataTransfer.files);
      }
    },
    [nichoSeleccionado, onSubirArchivos]
  );

  const manejarInputArchivos = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files && e.target.files.length > 0) {
        onSubirArchivos(e.target.files);
        if (inputArchivosRef.current) {
          inputArchivosRef.current.value = "";
        }
      }
    },
    [onSubirArchivos]
  );

  // ─── Scroll al tab activo ─────────────────────────────────────
  useEffect(() => {
    if (tabScrollRef.current && nichoSeleccionado) {
      const tabActivo = tabScrollRef.current.querySelector(`[data-nicho="${nichoSeleccionado}"]`);
      if (tabActivo) {
        tabActivo.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
      }
    }
  }, [nichoSeleccionado]);

  // ═══════════════════════════════════════════════════════════════════════
  // RENDERIZADO
  // ═══════════════════════════════════════════════════════════════════════

  return (
    <div className="space-y-6">
      {/* ═══════ SELECTOR HÍBRIDO: Mobile Dropdown / Desktop Tabs ═══════ */}
      <Card className="border-0 shadow-sm overflow-hidden">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-bold text-gray-900 flex items-center gap-2">
              <FolderOpen className="h-4 w-4 text-amber-500" />
              Nichos de Industria
            </CardTitle>
            <Badge className="bg-amber-100 text-amber-700 text-[9px] px-2 py-0 border-0 font-semibold shrink-0">
              {NICHOS_INDUSTRIALES.length} disponibles
            </Badge>
          </div>
          <p className="text-[10px] text-gray-400">
            Seleccione su industria para ver las reglas de cumplimiento y generar plantillas
          </p>
        </CardHeader>
        <CardContent>
          {/* ─── BARRA DE NICHOS: Siempre visible, scrollable horizontal ─── */}
          <div ref={tabScrollRef}>
            {/* Indicador de nicho activo (móvil) */}
            {nichoActual && (
              <div className="md:hidden flex items-center gap-2 mb-2 px-1">
                <span className="text-lg shrink-0">{nichoActual.emoji}</span>
                <span className="text-xs font-bold text-gray-800 truncate">{nichoActual.nombre}</span>
                <Badge className={`text-[8px] px-1.5 py-0 border-0 font-bold shrink-0 ${COLOR_CATEGORIA[nichoActual.categoria]?.bg || "bg-gray-100"} ${COLOR_CATEGORIA[nichoActual.categoria]?.text || "text-gray-600"}`}>
                  {nichoActual.standard}
                </Badge>
              </div>
            )}

            {/* Barra de tabs scrollable — visible en TODAS las pantallas */}
            <div
              className="flex gap-1 overflow-x-auto pb-2 scrollbar-thin relative"
              style={{
                WebkitOverflowScrolling: "touch",
                scrollbarWidth: "thin",
                maskImage: "linear-gradient(to right, black 90%, transparent 100%)",
                WebkitMaskImage: "linear-gradient(to right, black 90%, transparent 100%)",
              }}
            >
              {NICHOS_INDUSTRIALES.map((nicho) => {
                const activo = nichoSeleccionado === nicho.id;
                return (
                  <button
                    key={nicho.id}
                    data-nicho={nicho.id}
                    onClick={() => manejarSeleccion(nicho.id)}
                    className={`flex items-center gap-1.5 rounded-lg whitespace-nowrap transition-all shrink-0 ${
                      activo
                        ? "bg-[#1A1D2E] text-white shadow-md"
                        : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                    } ${
                      /* Móvil: compacto. Desktop: más espaciado */
                      "px-2 py-1.5 text-[10px] md:px-3 md:py-2 md:text-xs md:gap-2"
                    }`}
                  >
                    <span className="text-xs md:text-sm">{nicho.emoji}</span>
                    <span className="truncate max-w-[80px] md:max-w-[130px]">{nicho.nombre}</span>
                    {activo && (
                      <CheckCircle2 className="h-3 w-3 text-emerald-400 shrink-0" />
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ═══════ PANEL DE DETALLE DINÁMICO ═══════ */}
      {nichoActual ? (
        <div
          key={nichoActual.id}
          className={`space-y-6 transition-all duration-300 ease-out ${
            animacionActiva
              ? "opacity-100 translate-y-0"
              : "opacity-0 translate-y-2"
          }`}
        >
          {/* ─── Estándar de Cumplimiento ─── */}
          <Card className="border-0 shadow-sm overflow-hidden">
            <CardContent className="p-5">
              <div className="flex flex-col sm:flex-row sm:items-start gap-4">
                {/* Icono grande */}
                <div className={`w-14 h-14 rounded-2xl flex items-center justify-center shrink-0 ${
                  COLOR_CATEGORIA[nichoActual.categoria]?.bg || "bg-gray-100"
                }`}>
                  <span className="text-2xl">{nichoActual.emoji}</span>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <h3 className="text-base font-bold text-gray-900 truncate">
                      {nichoActual.nombre}
                    </h3>
                    <Badge className={`text-[8px] px-1.5 py-0 border-0 font-bold shrink-0 ${COLOR_CATEGORIA[nichoActual.categoria]?.bg || "bg-gray-100"} ${COLOR_CATEGORIA[nichoActual.categoria]?.text || "text-gray-600"}`}>
                      {ETIQUETA_CATEGORIA[nichoActual.categoria] || nichoActual.categoria}
                    </Badge>
                  </div>
                  {/* Caja de estándar */}
                  <div className="bg-amber-50 rounded-xl p-4 mt-3 overflow-hidden">
                    <p className="text-[10px] font-semibold text-amber-600 uppercase tracking-wider mb-1">
                      Estándar de Cumplimiento
                    </p>
                    <p className="text-sm font-bold text-amber-800">
                      {nichoActual.standardNombre}
                    </p>
                    <p className="text-[10px] text-amber-600 mt-1">
                      {nichoActual.standard} — {nichoActual.standardDescripcion}
                    </p>
                  </div>
                </div>
              </div>

              <Separator className="my-4" />

              {/* ─── Reglas de Dominio del Experto ─── */}
              <div>
                <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-3">
                  Reglas de Seguridad Aplicadas
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {nichoActual.reglas.map((regla, idx) => (
                    <div
                      key={idx}
                      className="flex items-start gap-2 bg-gray-50 rounded-lg p-2.5"
                    >
                      <ShieldCheck className="h-3.5 w-3.5 text-emerald-500 shrink-0 mt-0.5" />
                      <span className="text-[11px] text-gray-600 leading-tight">
                        {regla}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* ─── DENY Absolutos ─── */}
              {nichoActual.denyAbsolutos.length > 0 && (
                <div className="mt-4">
                  <p className="text-[10px] font-semibold text-red-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                    <AlertTriangle className="h-3.5 w-3.5" />
                    Denegaciones Absolutas — Bloqueadas desde la Raíz
                  </p>
                  <div className="space-y-2">
                    {nichoActual.denyAbsolutos.map((deny, idx) => (
                      <div
                        key={idx}
                        className="flex items-start gap-2 bg-red-50 border border-red-100 rounded-lg p-2.5"
                      >
                        <Lock className="h-3.5 w-3.5 text-red-500 shrink-0 mt-0.5" />
                        <span className="text-[11px] text-red-700 font-medium leading-tight">
                          {deny}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* ─── Zona de subida + Plantillas ─── */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Columna: Zona de subida */}
            <Card className="border-0 shadow-sm overflow-hidden">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-bold text-gray-900 flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-purple-500" />
                  Agente Yamil — Generador de Plantillas
                </CardTitle>
                <p className="text-[10px] text-gray-500">
                  Sube tus documentos y Yamil creará las plantillas para ti
                </p>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Drag & Drop zone */}
                <div
                  onDragOver={manejarDragOver}
                  onDragLeave={manejarDragLeave}
                  onDrop={manejarDrop}
                  className={`relative rounded-xl border-2 border-dashed p-8 text-center transition-all cursor-pointer overflow-hidden ${
                    dragActivo
                      ? "border-purple-400 bg-purple-50"
                      : "border-gray-200 bg-gray-50/50 hover:border-purple-300 hover:bg-purple-50/30"
                  }`}
                  onClick={() => {
                    if (inputArchivosRef.current) {
                      inputArchivosRef.current.click();
                    }
                  }}
                >
                  <input
                    ref={inputArchivosRef}
                    type="file"
                    multiple
                    accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.md,.json"
                    className="hidden"
                    onChange={manejarInputArchivos}
                  />
                  <div className="space-y-3">
                    <div
                      className={`w-14 h-14 rounded-full flex items-center justify-center mx-auto ${
                        dragActivo ? "bg-purple-100" : "bg-gray-100"
                      }`}
                    >
                      {subiendoArchivos ? (
                        <RefreshCw className="h-6 w-6 text-purple-500 animate-spin" />
                      ) : (
                        <Upload
                          className={`h-6 w-6 ${dragActivo ? "text-purple-500" : "text-gray-400"}`}
                        />
                      )}
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-gray-700">
                        {subiendoArchivos
                          ? "Procesando archivos..."
                          : dragActivo
                            ? "Suelta los archivos aquí"
                            : "Arrastra archivos aquí o haz clic para seleccionar"}
                      </p>
                      <p className="text-[10px] text-gray-400 mt-1">
                        PDF, Word, Excel, TXT, CSV, Markdown, JSON — Máximo 10 MB
                      </p>
                    </div>
                  </div>
                </div>

                {/* Lista de archivos subidos */}
                {archivosSubidos.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
                      Archivos Subidos
                    </p>
                    <ScrollArea className="max-h-48">
                      <div className="space-y-1.5">
                        {archivosSubidos.map((archivo, idx) => (
                          <div
                            key={`${archivo.nombre}-${idx}`}
                            className={`flex items-center gap-3 rounded-lg border p-2.5 overflow-hidden ${
                              archivo.estado === "completado"
                                ? "border-emerald-200 bg-emerald-50/50"
                                : archivo.estado === "error"
                                  ? "border-red-200 bg-red-50/50"
                                  : archivo.estado === "procesando"
                                    ? "border-amber-200 bg-amber-50/50"
                                    : "border-gray-200 bg-gray-50/50"
                            }`}
                          >
                            <div
                              className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
                                archivo.estado === "completado"
                                  ? "bg-emerald-100"
                                  : archivo.estado === "error"
                                    ? "bg-red-100"
                                    : "bg-amber-100"
                              }`}
                            >
                              {archivo.estado === "completado" ? (
                                <FileText className="h-4 w-4 text-emerald-600" />
                              ) : archivo.estado === "procesando" ? (
                                <FileUp className="h-4 w-4 text-amber-600 animate-pulse" />
                              ) : (
                                <FileUp className="h-4 w-4 text-gray-400" />
                              )}
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className="text-[11px] font-medium text-gray-700 truncate">
                                {archivo.nombre}
                              </p>
                              <p className="text-[9px] text-gray-400">
                                {formatoTamañoArchivo(archivo.tamaño)} •{" "}
                                {archivo.estado === "completado"
                                  ? "Completado"
                                  : archivo.estado === "procesando"
                                    ? "Procesando..."
                                    : archivo.estado === "error"
                                      ? "Error"
                                      : "Recibido"}
                              </p>
                            </div>
                            {archivo.estado === "completado" ? (
                              <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                            ) : archivo.estado === "procesando" ? (
                              <RefreshCw className="h-4 w-4 text-amber-500 animate-spin shrink-0" />
                            ) : archivo.estado === "error" ? (
                              <XCircle className="h-4 w-4 text-red-500 shrink-0" />
                            ) : (
                              <Clock className="h-4 w-4 text-gray-300 shrink-0" />
                            )}
                          </div>
                        ))}
                      </div>
                    </ScrollArea>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Columna: Plantillas generadas */}
            <Card className="border-0 shadow-sm overflow-hidden">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-bold text-gray-900 flex items-center gap-2">
                    <FileText className="h-4 w-4 text-emerald-500" />
                    Plantillas Generadas
                  </CardTitle>
                  <Badge className="bg-emerald-100 text-emerald-700 text-[9px] px-2 py-0 border-0 font-semibold shrink-0">
                    {plantillas.length} plantilla{plantillas.length !== 1 ? "s" : ""}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                {cargandoPlantillas ? (
                  <div className="py-16 text-center">
                    <RefreshCw className="h-8 w-8 text-gray-300 mx-auto mb-3 animate-spin" />
                    <p className="text-xs text-gray-400">Cargando plantillas...</p>
                  </div>
                ) : plantillas.length === 0 ? (
                  <div className="py-16 text-center">
                    <Sparkles className="h-12 w-12 text-gray-200 mx-auto mb-3" />
                    <p className="text-sm font-medium text-gray-400">Sin plantillas aún</p>
                    <p className="text-[10px] text-gray-300 mt-1 max-w-[240px] mx-auto">
                      Sube documentos en la zona de carga y Yamil generará las plantillas automáticamente
                    </p>
                  </div>
                ) : (
                  <ScrollArea className="max-h-[520px]">
                    <div className="space-y-3 pr-1">
                      {plantillas.map((plantilla) => (
                        <div
                          key={plantilla.id}
                          className={`rounded-xl border-2 p-4 transition-all overflow-hidden ${
                            plantilla.estado === "lista"
                              ? "border-emerald-200 bg-emerald-50/30"
                              : "border-amber-200 bg-amber-50/30"
                          }`}
                        >
                          <div className="flex items-start gap-3">
                            <div
                              className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${
                                plantilla.estado === "lista"
                                  ? "bg-emerald-100 text-emerald-600"
                                  : "bg-amber-100 text-amber-600"
                              }`}
                            >
                              {plantilla.estado === "lista" ? (
                                <FileCheck className="h-5 w-5" />
                              ) : (
                                <FileText className="h-5 w-5" />
                              )}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center justify-between gap-2 mb-1">
                                <p className="text-xs font-bold text-gray-800 truncate">
                                  {plantilla.nombre}
                                </p>
                                <Badge
                                  className={`text-[8px] px-1.5 py-0 border-0 font-bold shrink-0 ${
                                    plantilla.estado === "lista"
                                      ? "bg-emerald-100 text-emerald-700"
                                      : "bg-amber-100 text-amber-700"
                                  }`}
                                >
                                  {plantilla.estado === "lista" ? "LISTA" : "BORRADOR"}
                                </Badge>
                              </div>
                              <p className="text-[10px] text-gray-500 line-clamp-2">
                                {plantilla.descripcion}
                              </p>
                              <div className="flex items-center gap-3 mt-2 text-[9px] text-gray-400">
                                <span className="flex items-center gap-1">
                                  <FileText className="h-3 w-3 shrink-0" />
                                  {plantilla.tipo}
                                </span>
                                <span className="flex items-center gap-1">
                                  <Clock className="h-3 w-3 shrink-0" />
                                  {tiempoRelativo(plantilla.fechaCreacion)}
                                </span>
                              </div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </ScrollArea>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      ) : (
        /* ─── Estado vacío ─── */
        <Card className="border-0 shadow-sm overflow-hidden">
          <CardContent className="py-16 text-center">
            <FolderOpen className="h-16 w-16 text-gray-200 mx-auto mb-4" />
            <p className="text-lg font-semibold text-gray-400">
              Seleccione un nicho de industria
            </p>
            <p className="text-sm text-gray-300 mt-1 max-w-[360px] mx-auto">
              Elija uno de los {NICHOS_INDUSTRIALES.length} nichos disponibles para ver su estándar de cumplimiento,
              subir documentos y generar plantillas con el agente Yamil.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
