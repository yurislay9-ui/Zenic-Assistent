// ═══════════════════════════════════════════════════════════════════════════════
// TIPOS — ApisMcpTab
// ═══════════════════════════════════════════════════════════════════════════════

export interface ApiCredentialData {
  id: string;
  name: string;
  platform: string;
  type: string;
  apiKey: string;
  apiSecret: string | null;
  endpoint: string | null;
  username: string | null;
  password: string | null;
  scope: string;
  isActive: boolean;
  lastVerified: string | null;
  verifyStatus: string;
  verifyMessage: string | null;
  metadata: string;
  createdAt: string;
  updatedAt: string;
}

export interface McpServerData {
  id: string;
  name: string;
  displayName: string;
  description: string;
  url: string;
  protocol: string;
  status: string;
  healthCheckUrl: string | null;
  authType: string;
  capabilities: string[];
  toolCount?: number;
}

export interface ServiceCred {
  id: string;
  serviceId: string;
  nombre: string;
  campos: Record<string, string>;
  createdAt: string;
}
