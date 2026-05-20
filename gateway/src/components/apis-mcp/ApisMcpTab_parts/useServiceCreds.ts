"use client";

import { useState, useCallback } from "react";
import type { ServiceCred } from "./_types";
import { EXTERNAL_SERVICES } from "./_constants";

export function useServiceCreds() {
  const [serviceCreds, setServiceCreds] = useState<ServiceCred[]>([]);
  const [addServiceDialogOpen, setAddServiceDialogOpen] = useState(false);
  const [selectedService, setSelectedService] = useState<string>("jira");
  const [serviceFields, setServiceFields] = useState<Record<string, string>>({});
  const [showServiceFields, setShowServiceFields] = useState<Record<string, boolean>>({});

  // ─── Cargar datos ─────────────────────────────────────────────────────
  const loadServiceCreds = useCallback(async (signal?: AbortSignal) => {
    try {
      const res = await fetch("/api/dashboard/service-credentials", { signal });
      if (res.ok) {
        const data = await res.json();
        setServiceCreds(data.credentials || []);
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      console.error("Error cargando credenciales de servicio:", err);
    }
  }, []);

  // ─── Guardar credencial de servicio externo ────────────────────────────
  // SECURITY: Ya no usa localStorage. Envía al API endpoint cifrado.
  // INVARIANT 4 — defensa en profundidad, la regla DENY es absoluta.
  const guardarCredServicio = async () => {
    const service = EXTERNAL_SERVICES.find((s) => s.id === selectedService);
    if (!service) return;

    const hasValues = Object.values(serviceFields).some((v) => v.trim() !== "");
    if (!hasValues) return;

    try {
      const res = await fetch("/api/dashboard/service-credentials", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          serviceId: selectedService,
          nombre: service.nombre,
          campos: serviceFields,
        }),
      });

      if (res.ok) {
        setServiceFields({});
        setAddServiceDialogOpen(false);
        loadServiceCreds();
      } else {
        const data = await res.json();
        console.error("Error guardando credencial de servicio:", data.error);
      }
    } catch (err) {
      console.error("Error guardando credencial de servicio:", err);
    }
  };

  const eliminarCredServicio = async (id: string) => {
    try {
      const res = await fetch(`/api/dashboard/service-credentials?id=${id}`, {
        method: "DELETE",
      });
      if (res.ok) {
        loadServiceCreds();
      }
    } catch (err) {
      console.error("Error eliminando credencial de servicio:", err);
    }
  };

  return {
    serviceCreds,
    addServiceDialogOpen,
    selectedService,
    serviceFields,
    showServiceFields,
    setAddServiceDialogOpen,
    setSelectedService,
    setServiceFields,
    setShowServiceFields,
    loadServiceCreds,
    guardarCredServicio,
    eliminarCredServicio,
  };
}
