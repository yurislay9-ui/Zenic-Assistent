// ─── Zenic-Agents v3 — MCP Gateway Type System ──────────────────────
// UI Configuration Maps for enums

import type { RiskLevel, ExecStatus, AuditSeverity, ToolCategory } from "./_enums";

export const RISK_LEVEL_CONFIG: Record<RiskLevel, {
  label: string;
  color: string;
  bgColor: string;
  requiresApproval: boolean;
  maxRetries: number;
}> = {
  low: { label: "Low", color: "text-green-700 dark:text-green-400", bgColor: "bg-green-100 dark:bg-green-900/30", requiresApproval: false, maxRetries: 3 },
  medium: { label: "Medium", color: "text-yellow-700 dark:text-yellow-400", bgColor: "bg-yellow-100 dark:bg-yellow-900/30", requiresApproval: false, maxRetries: 2 },
  high: { label: "High", color: "text-orange-700 dark:text-orange-400", bgColor: "bg-orange-100 dark:bg-orange-900/30", requiresApproval: true, maxRetries: 1 },
  critical: { label: "Critical", color: "text-red-700 dark:text-red-400", bgColor: "bg-red-100 dark:bg-red-900/30", requiresApproval: true, maxRetries: 0 },
};

export const EXEC_STATUS_CONFIG: Record<ExecStatus, {
  label: string;
  color: string;
  bgColor: string;
}> = {
  pending: { label: "Pending", color: "text-gray-700 dark:text-gray-300", bgColor: "bg-gray-100 dark:bg-gray-800" },
  approved: { label: "Approved", color: "text-blue-700 dark:text-blue-400", bgColor: "bg-blue-100 dark:bg-blue-900/30" },
  running: { label: "Running", color: "text-cyan-700 dark:text-cyan-400", bgColor: "bg-cyan-100 dark:bg-cyan-900/30" },
  completed: { label: "Completed", color: "text-green-700 dark:text-green-400", bgColor: "bg-green-100 dark:bg-green-900/30" },
  failed: { label: "Failed", color: "text-red-700 dark:text-red-400", bgColor: "bg-red-100 dark:bg-red-900/30" },
  denied: { label: "Denied", color: "text-rose-700 dark:text-rose-400", bgColor: "bg-rose-100 dark:bg-rose-900/30" },
  timeout: { label: "Timeout", color: "text-amber-700 dark:text-amber-400", bgColor: "bg-amber-100 dark:bg-amber-900/30" },
};

export const SEVERITY_CONFIG: Record<AuditSeverity, {
  label: string;
  color: string;
  bgColor: string;
  icon: string;
}> = {
  debug: { label: "Debug", color: "text-gray-500", bgColor: "bg-gray-50", icon: "Bug" },
  info: { label: "Info", color: "text-blue-600", bgColor: "bg-blue-50", icon: "Info" },
  warn: { label: "Warning", color: "text-yellow-600", bgColor: "bg-yellow-50", icon: "AlertTriangle" },
  error: { label: "Error", color: "text-red-600", bgColor: "bg-red-50", icon: "XCircle" },
  critical: { label: "Critical", color: "text-red-800", bgColor: "bg-red-100", icon: "ShieldAlert" },
};

export const TOOL_CATEGORY_CONFIG: Record<ToolCategory, {
  label: string;
  icon: string;
  color: string;
}> = {
  data: { label: "Data", icon: "Database", color: "text-violet-600" },
  communication: { label: "Communication", icon: "MessageSquare", color: "text-sky-600" },
  compute: { label: "Compute", icon: "Cpu", color: "text-orange-600" },
  storage: { label: "Storage", icon: "HardDrive", color: "text-emerald-600" },
  external: { label: "External", icon: "Globe", color: "text-pink-600" },
  security: { label: "Security", icon: "Shield", color: "text-red-600" },
  monitoring: { label: "Monitoring", icon: "Activity", color: "text-cyan-600" },
};
