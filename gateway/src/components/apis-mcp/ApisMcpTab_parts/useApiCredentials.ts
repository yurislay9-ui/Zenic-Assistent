"use client";

import { useState, useCallback } from "react";
import type { ApiCredentialData } from "./_types";

const INITIAL_NEW_CRED = {
  name: "",
  platform: "mcp-gateway",
  type: "api_key",
  apiKey: "",
  apiSecret: "",
  endpoint: "",
  username: "",
  password: "",
};

export function useApiCredentials() {
  const [credentials, setCredentials] = useState<ApiCredentialData[]>([]);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const [showSecret, setShowSecret] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [newCred, setNewCred] = useState({ ...INITIAL_NEW_CRED });

  // ─── Cargar datos ─────────────────────────────────────────────────────
  const loadCredentials = useCallback(async (signal?: AbortSignal) => {
    try {
      const res = await fetch("/api/dashboard/api-credentials", { signal });
      if (res.ok) {
        const data = await res.json();
        setCredentials(data.credentials || []);
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      console.error("Error cargando credenciales:", err);
    }
  }, []);

  // ─── Crear credencial API ──────────────────────────────────────────────
  const crearCredencial = async () => {
    if (!newCred.name || !newCred.apiKey) return;

    try {
      const res = await fetch("/api/dashboard/api-credentials", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newCred.name,
          platform: newCred.platform,
          type: newCred.type,
          apiKey: newCred.apiKey,
          apiSecret: newCred.apiSecret || null,
          endpoint: newCred.endpoint || null,
          username: newCred.type === "basic_auth" ? newCred.username : null,
          password: newCred.type === "basic_auth" ? newCred.password : null,
        }),
      });

      if (res.ok) {
        setAddDialogOpen(false);
        setNewCred({ ...INITIAL_NEW_CRED });
        loadCredentials();
      }
    } catch (err) {
      console.error("Error creando credencial:", err);
    }
  };

  // ─── Eliminar credencial API ───────────────────────────────────────────
  const eliminarCredencial = async (id: string) => {
    try {
      const res = await fetch(`/api/dashboard/api-credentials?id=${id}`, {
        method: "DELETE",
      });
      if (res.ok) {
        loadCredentials();
      }
    } catch (err) {
      console.error("Error eliminando credencial:", err);
    }
  };

  // ─── Testear credencial API ────────────────────────────────────────────
  const testearCredencial = async (id: string) => {
    setTestingId(id);
    try {
      const res = await fetch("/api/dashboard/api-credentials/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id }),
      });
      if (res.ok) {
        loadCredentials();
      }
    } catch (err) {
      console.error("Error testeando credencial:", err);
    } finally {
      setTestingId(null);
    }
  };

  return {
    credentials,
    testingId,
    addDialogOpen,
    showApiKey,
    showSecret,
    showPassword,
    newCred,
    setAddDialogOpen,
    setShowApiKey,
    setShowSecret,
    setShowPassword,
    setNewCred,
    loadCredentials,
    crearCredencial,
    eliminarCredencial,
    testearCredencial,
  };
}
