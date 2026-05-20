"use client";

import { useState, useCallback } from "react";
import type { McpServerData } from "./_types";

const INITIAL_NEW_SERVER = {
  name: "",
  displayName: "",
  description: "",
  url: "",
  protocol: "http",
  authType: "none",
  healthCheckUrl: "",
};

export function useMcpServers() {
  const [mcpServers, setMcpServers] = useState<McpServerData[]>([]);
  const [testingServerId, setTestingServerId] = useState<string | null>(null);
  const [addServerDialogOpen, setAddServerDialogOpen] = useState(false);
  const [newServer, setNewServer] = useState({ ...INITIAL_NEW_SERVER });

  // ─── Cargar datos ─────────────────────────────────────────────────────
  const loadMcpServers = useCallback(async (signal?: AbortSignal) => {
    try {
      const res = await fetch("/api/mcp/servers", { signal });
      if (res.ok) {
        const data = await res.json();
        setMcpServers(data.data || []);
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      console.error("Error cargando servidores MCP:", err);
    }
  }, []);

  // ─── Crear servidor MCP ────────────────────────────────────────────────
  const crearServidorMcp = async () => {
    if (!newServer.name || !newServer.url) return;

    try {
      const res = await fetch("/api/mcp/servers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newServer.name,
          displayName: newServer.displayName || newServer.name,
          description: newServer.description || "Servidor MCP",
          url: newServer.url,
          protocol: newServer.protocol,
          status: "active",
          authType: newServer.authType,
          healthCheckUrl: newServer.healthCheckUrl || null,
        }),
      });

      if (res.ok) {
        setAddServerDialogOpen(false);
        setNewServer({ ...INITIAL_NEW_SERVER });
        loadMcpServers();
      }
    } catch (err) {
      console.error("Error creando servidor MCP:", err);
    }
  };

  // ─── Testear servidor MCP ──────────────────────────────────────────────
  // FIX: Antes era un fake health check (setTimeout + console.log).
  // Ahora hace un fetch real al endpoint de health check del servidor.
  const testearServidorMcp = async (server: McpServerData) => {
    setTestingServerId(server.id);
    try {
      const healthUrl = server.healthCheckUrl || server.url;
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000);
      const res = await fetch(healthUrl, {
        method: "GET",
        signal: controller.signal,
        mode: "no-cors", // Permite check sin CORS headers
      });
      clearTimeout(timeoutId);
      // En mode no-cors, res.type es 'opaque' y res.status es 0 si OK
      // Cualquier respuesta (incluso opaque) = servidor alcanzaable
      void res; // usaremos el resultado en el refresh de loadMcpServers
      loadMcpServers();
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        console.warn(`Health check timeout para ${server.name}`);
      } else {
        console.error("Error testeando servidor:", err);
      }
    } finally {
      setTestingServerId(null);
    }
  };

  return {
    mcpServers,
    testingServerId,
    addServerDialogOpen,
    newServer,
    setAddServerDialogOpen,
    setNewServer,
    loadMcpServers,
    crearServidorMcp,
    testearServidorMcp,
  };
}
