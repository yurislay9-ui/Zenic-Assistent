"use client";

import { useState, useMemo, useCallback, useRef, useEffect } from "react";
import type { NichoIndustrial, PlantillaNicho, ArchivoSubido } from "./NichosSelector_parts/_types";
import { NICHOS_INDUSTRIALES_PART1 } from "./NichosSelector_parts/_constants";
import { NICHOS_INDUSTRIALES_PART2 } from "./NichosSelector_parts/_constants2";
import NichoTabBar from "./NichosSelector_parts/_NichoTabBar";
import NichoDetailPanel from "./NichosSelector_parts/_NichoDetailPanel";
import UploadZone from "./NichosSelector_parts/_UploadZone";
import TemplatesList, { NichoEmptyState } from "./NichosSelector_parts/_TemplatesList";

// Re-join the split constants
const NICHOS_INDUSTRIALES: NichoIndustrial[] = [...NICHOS_INDUSTRIALES_PART1, ...NICHOS_INDUSTRIALES_PART2];

interface NichosSelectorProps {
  nichosApi?: Array<{
    id: string;
    name: string;
    icon: string;
    standard: string;
    standardName: string;
    active: boolean;
    rules: string[];
  }>;
  plantillas: PlantillaNicho[];
  archivosSubidos: ArchivoSubido[];
  onSeleccionarNicho: (nichoId: string) => void;
  onSubirArchivos: (archivos: FileList | File[]) => void;
  subiendoArchivos: boolean;
  cargandoPlantillas: boolean;
  nichoSeleccionado: string | null;
}

export default function NichosSelector({
  plantillas,
  archivosSubidos,
  onSeleccionarNicho,
  onSubirArchivos,
  subiendoArchivos,
  cargandoPlantillas,
  nichoSeleccionado,
}: NichosSelectorProps) {
  const [animacionActiva, setAnimacionActiva] = useState(false);
  const [dragActivo, setDragActivo] = useState(false);
  const inputArchivosRef = useRef<HTMLInputElement>(null);
  const tabScrollRef = useRef<HTMLDivElement>(null);

  const nichoActual = useMemo(
    () => NICHOS_INDUSTRIALES.find((n) => n.id === nichoSeleccionado) ?? null,
    [nichoSeleccionado]
  );

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

  useEffect(() => {
    if (tabScrollRef.current && nichoSeleccionado) {
      const tabActivo = tabScrollRef.current.querySelector(`[data-nicho="${nichoSeleccionado}"]`);
      if (tabActivo) {
        tabActivo.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
      }
    }
  }, [nichoSeleccionado]);

  return (
    <div className="space-y-6">
      <NichoTabBar
        nichos={NICHOS_INDUSTRIALES}
        nichoSeleccionado={nichoSeleccionado}
        nichoActual={nichoActual}
        onSeleccionar={manejarSeleccion}
        tabScrollRef={tabScrollRef}
      />

      {nichoActual ? (
        <>
          <NichoDetailPanel nicho={nichoActual} animacionActiva={animacionActiva} />

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <UploadZone
              dragActivo={dragActivo}
              subiendoArchivos={subiendoArchivos}
              archivosSubidos={archivosSubidos}
              nichoSeleccionado={nichoSeleccionado}
              onDragOver={manejarDragOver}
              onDragLeave={manejarDragLeave}
              onDrop={manejarDrop}
              onClickUpload={() => inputArchivosRef.current?.click()}
              onFileChange={manejarInputArchivos}
              inputRef={inputArchivosRef}
            />
            <TemplatesList
              plantillas={plantillas}
              cargandoPlantillas={cargandoPlantillas}
              totalNichos={NICHOS_INDUSTRIALES.length}
            />
          </div>
        </>
      ) : (
        <NichoEmptyState totalNichos={NICHOS_INDUSTRIALES.length} />
      )}
    </div>
  );
}
