import { db } from "@/lib/db";

/**
 * Seed MCP servers, tools, executions, and metric series.
 * Sections 4–6 and 10 of the original monolithic seed route.
 */
export async function seedPlaybookData(adminUserId: string | undefined): Promise<string[]> {
  const results: string[] = [];

  // ─── 4. Seed 5 MCP Servers ───────────────────────────────────────
  const serverDefs = [
    { name: "primary-gateway", displayName: "Primary Gateway", description: "Main MCP gateway server handling tool routing and execution for core services", url: "https://mcp-gateway.zenic.dev", protocol: "http", status: "active", healthCheckUrl: "https://mcp-gateway.zenic.dev/health", authType: "api_key", authConfig: JSON.stringify({ header: "X-API-Key", rotationDays: 30 }), capabilities: JSON.stringify(["tool_execution", "streaming", "batch", "cancellation"]), metadata: JSON.stringify({ region: "us-east-1", version: "3.2.1", uptime: "99.97%" }) },
    { name: "analytics-relay", displayName: "Analytics Relay", description: "Secondary relay server for analytics and monitoring tool execution", url: "wss://analytics.zenic.dev/ws", protocol: "websocket", status: "active", healthCheckUrl: "https://analytics.zenic.dev/health", authType: "oauth2", authConfig: JSON.stringify({ provider: "internal", scopes: ["read", "execute"] }), capabilities: JSON.stringify(["analytics", "monitoring", "realtime", "alerts"]), metadata: JSON.stringify({ region: "eu-west-1", version: "2.1.0", uptime: "99.85%" }) },
    { name: "data-lake-connector", displayName: "Data Lake Connector", description: "Connector service for data lake read/write operations with schema validation", url: "https://datalake.zenic.dev", protocol: "http", status: "active", healthCheckUrl: "https://datalake.zenic.dev/health", authType: "mtls", authConfig: JSON.stringify({ certRotation: "30d" }), capabilities: JSON.stringify(["data_read", "data_write", "schema_validation", "batch_import"]), metadata: JSON.stringify({ region: "us-west-2", version: "1.3.0", uptime: "99.92%" }) },
    { name: "notification-hub", displayName: "Notification Hub", description: "Central notification service for email, SMS, and push delivery", url: "https://notify.zenic.dev", protocol: "http", status: "unhealthy", healthCheckUrl: "https://notify.zenic.dev/health", authType: "api_key", authConfig: JSON.stringify({ header: "X-Notify-Key" }), capabilities: JSON.stringify(["email", "sms", "push", "webhook"]), metadata: JSON.stringify({ region: "ap-south-1", version: "1.1.0", uptime: "97.5%", lastError: "SMTP timeout" }) },
    { name: "compute-cluster", displayName: "Compute Cluster", description: "GPU-enabled compute cluster for ML inference and batch processing", url: "grpc://compute.zenic.dev:50051", protocol: "grpc", status: "active", healthCheckUrl: "https://compute.zenic.dev/health", authType: "mtls", authConfig: JSON.stringify({ certRotation: "7d" }), capabilities: JSON.stringify(["ml_inference", "batch_processing", "gpu_compute", "auto_scaling"]), metadata: JSON.stringify({ region: "us-east-1", version: "2.0.0", uptime: "99.99%", gpuAvailable: true }) },
  ];

  const serverIds: string[] = [];
  for (const sd of serverDefs) {
    const server = await db.mcpServer.upsert({ where: { name: sd.name }, update: {}, create: sd });
    serverIds.push(server.id);
  }
  results.push(`Servers ensured (${serverIds.length} total)`);

  // ─── 5. Seed 10 MCP Tools ────────────────────────────────────────
  const toolDefs = [
    { name: "weather_lookup", displayName: "Weather Lookup", description: "Retrieve current weather conditions and forecasts for any global location", category: "external", version: "2.3.0", icon: "Cloud", endpoint: "/api/tools/weather", method: "POST", inputSchema: JSON.stringify({ type: "object", properties: { location: { type: "string" }, units: { type: "string", enum: ["celsius", "fahrenheit"] } }, required: ["location"] }), timeout: 10000, retries: 2, rateLimit: 60, riskLevel: "low", status: "active", requiresApproval: false, tags: JSON.stringify(["weather", "external", "api"]), metadata: JSON.stringify({ provider: "OpenWeatherMap", cacheTTL: 300 }), serverId: serverIds[0] },
    { name: "db_query", displayName: "Database Query", description: "Execute read-only SQL queries against authorized database connections with result pagination", category: "data", version: "1.8.2", icon: "Database", endpoint: "/api/tools/db/query", method: "POST", inputSchema: JSON.stringify({ type: "object", properties: { query: { type: "string" }, connectionId: { type: "string" }, limit: { type: "number", default: 100 } }, required: ["query", "connectionId"] }), timeout: 30000, retries: 1, rateLimit: 30, riskLevel: "medium", status: "active", requiresApproval: true, tags: JSON.stringify(["database", "sql", "read-only"]), metadata: JSON.stringify({ supportedDbs: ["postgresql", "mysql", "sqlite"] }), serverId: serverIds[0] },
    { name: "file_read", displayName: "File Reader", description: "Read file contents from authorized storage paths with format detection and encoding support", category: "storage", version: "1.5.1", icon: "FileText", endpoint: "/api/tools/file/read", method: "POST", inputSchema: JSON.stringify({ type: "object", properties: { path: { type: "string" }, encoding: { type: "string", default: "utf-8" } }, required: ["path"] }), timeout: 10000, retries: 2, rateLimit: 100, riskLevel: "medium", status: "active", requiresApproval: false, tags: JSON.stringify(["file", "storage", "read"]), metadata: JSON.stringify({ maxFileSize: "10MB", supportedEncodings: ["utf-8", "ascii", "base64"] }), serverId: serverIds[2] },
    { name: "email_send", displayName: "Email Sender", description: "Send templated emails to internal and external recipients with delivery tracking", category: "communication", version: "3.1.0", icon: "Mail", endpoint: "/api/tools/email/send", method: "POST", inputSchema: JSON.stringify({ type: "object", properties: { to: { type: "array", items: { type: "string" } }, subject: { type: "string" }, template: { type: "string" } }, required: ["to", "subject"] }), timeout: 15000, retries: 3, rateLimit: 20, riskLevel: "high", status: "active", requiresApproval: true, tags: JSON.stringify(["email", "communication", "notifications"]), metadata: JSON.stringify({ provider: "SendGrid", trackingEnabled: true }), serverId: serverIds[3] },
    { name: "compute_task", displayName: "Compute Task", description: "Submit and manage compute tasks including data processing, ML inference, and batch operations", category: "compute", version: "2.0.0", icon: "Cpu", endpoint: "/api/tools/compute", method: "POST", inputSchema: JSON.stringify({ type: "object", properties: { taskType: { type: "string", enum: ["data_processing", "ml_inference", "batch"] }, payload: { type: "object" } }, required: ["taskType", "payload"] }), timeout: 120000, retries: 1, rateLimit: 10, riskLevel: "high", status: "active", requiresApproval: true, tags: JSON.stringify(["compute", "ml", "processing"]), metadata: JSON.stringify({ maxMemory: "4GB", gpuAvailable: true }), serverId: serverIds[4] },
    { name: "security_scan", displayName: "Security Scanner", description: "Run vulnerability and compliance scans on target resources with detailed finding reports", category: "security", version: "1.2.0", icon: "Shield", endpoint: "/api/tools/security/scan", method: "POST", inputSchema: JSON.stringify({ type: "object", properties: { target: { type: "string" }, scanType: { type: "string", enum: ["vulnerability", "compliance", "full"] } }, required: ["target", "scanType"] }), timeout: 60000, retries: 1, rateLimit: 5, riskLevel: "critical", status: "active", requiresApproval: true, tags: JSON.stringify(["security", "scanning", "compliance"]), metadata: JSON.stringify({ scanEngines: ["nmap", "owasp-zap", "trivy"] }), serverId: serverIds[0] },
    { name: "metrics_collect", displayName: "Metrics Collector", description: "Collect and aggregate system metrics from monitoring endpoints with customizable time ranges", category: "monitoring", version: "1.4.0", icon: "Activity", endpoint: "/api/tools/metrics/collect", method: "POST", inputSchema: JSON.stringify({ type: "object", properties: { source: { type: "string" }, timeRange: { type: "string" }, granularity: { type: "string", default: "5m" } }, required: ["source", "timeRange"] }), timeout: 20000, retries: 2, rateLimit: 50, riskLevel: "low", status: "active", requiresApproval: false, tags: JSON.stringify(["monitoring", "metrics", "observability"]), metadata: JSON.stringify({ backends: ["prometheus", "grafana", "datadog"] }), serverId: serverIds[1] },
    { name: "webhook_dispatch", displayName: "Webhook Dispatcher", description: "Dispatch webhook events to registered endpoints with retry logic and delivery confirmation", category: "communication", version: "2.2.1", icon: "Webhook", endpoint: "/api/tools/webhook/dispatch", method: "POST", inputSchema: JSON.stringify({ type: "object", properties: { url: { type: "string" }, event: { type: "string" }, payload: { type: "object" } }, required: ["url", "event", "payload"] }), timeout: 10000, retries: 3, rateLimit: 100, riskLevel: "medium", status: "active", requiresApproval: false, tags: JSON.stringify(["webhook", "integration", "events"]), metadata: JSON.stringify({ maxRetries: 5, retryBackoff: "exponential" }), serverId: serverIds[0] },
    { name: "inventory_check", displayName: "Inventory Checker", description: "Check real-time inventory levels across warehouses and trigger restock alerts when thresholds are breached", category: "data", version: "1.1.0", icon: "Package", endpoint: "/api/tools/inventory/check", method: "POST", inputSchema: JSON.stringify({ type: "object", properties: { sku: { type: "string" }, warehouse: { type: "string" } }, required: ["sku"] }), timeout: 8000, retries: 2, rateLimit: 80, riskLevel: "low", status: "active", requiresApproval: false, tags: JSON.stringify(["inventory", "warehouse", "data"]), metadata: JSON.stringify({ realtimeSync: true, alertThreshold: 5 }), serverId: serverIds[2] },
    { name: "schema_mapper", displayName: "Schema Mapper", description: "Map and transform data schemas between systems with drift detection and auto-mitigation proposals", category: "data", version: "1.0.0", icon: "GitBranch", endpoint: "/api/tools/schema/mapper", method: "POST", inputSchema: JSON.stringify({ type: "object", properties: { sourceSchema: { type: "string" }, targetSchema: { type: "string" }, autoApply: { type: "boolean", default: false } }, required: ["sourceSchema", "targetSchema"] }), timeout: 15000, retries: 1, rateLimit: 20, riskLevel: "medium", status: "testing", requiresApproval: true, tags: JSON.stringify(["schema", "mapping", "drift-detection"]), metadata: JSON.stringify({ driftDetection: true, autoPropose: true }), serverId: serverIds[2] },
  ];

  const toolIds: string[] = [];
  for (const td of toolDefs) {
    const tool = await db.mcpTool.upsert({ where: { name: td.name }, update: {}, create: td });
    toolIds.push(tool.id);
  }
  results.push(`Tools ensured (${toolIds.length} total)`);

  // ─── 6. Seed 50 ToolExecutions ───────────────────────────────────
  const existingExecCount = await db.toolExecution.count();
  if (existingExecCount < 50 && toolIds.length > 0 && adminUserId) {
    const now = Date.now();
    const executionData: Array<{ toolIdx: number; status: string; duration: number | null; verdict: string | null; errorMessage: string | null; verdictReason: string | null; hoursAgo: number }> = [];
    const statusMix: Array<{ status: string; verdict: string | null; weight: number }> = [
      { status: "completed", verdict: "allow", weight: 35 },
      { status: "completed", verdict: "conditional", weight: 5 },
      { status: "failed", verdict: "allow", weight: 3 },
      { status: "denied", verdict: "deny", weight: 4 },
      { status: "timeout", verdict: "allow", weight: 2 },
      { status: "pending", verdict: null, weight: 1 },
    ];
    for (let i = 0; i < 50; i++) {
      const rand = Math.random() * 50;
      let cumulative = 0;
      let chosen = statusMix[0];
      for (const sm of statusMix) { cumulative += sm.weight; if (rand < cumulative) { chosen = sm; break; } }
      const durationMap: Record<string, number | null> = { completed: Math.floor(Math.random() * 3000) + 50, failed: Math.floor(Math.random() * 5000) + 2000, denied: null, timeout: 30000, pending: null };
      const errorMap: Record<string, string | null> = { completed: null, failed: ["Connection timeout after retries", "Service unavailable", "Rate limit exceeded", "Internal server error"][Math.floor(Math.random() * 4)], denied: null, timeout: "Execution exceeded 30s timeout", pending: null };
      const reasonMap: Record<string, string | null> = { deny: ["Blocked by deny-external-after-hours policy", "Insufficient permissions", "Risk level exceeds threshold", "Quota exceeded"][Math.floor(Math.random() * 4)], conditional: "Requires approval per business-hours-only policy", allow: null };
      executionData.push({ toolIdx: i % toolIds.length, status: chosen.status, duration: durationMap[chosen.status] ?? null, verdict: chosen.verdict, errorMessage: errorMap[chosen.status], verdictReason: chosen.verdict ? reasonMap[chosen.verdict] : null, hoursAgo: Math.random() * 48 });
    }
    executionData.sort((a, b) => a.hoursAgo - b.hoursAgo);
    await db.$transaction(
      executionData.map((exec) => {
        const toolId = toolIds[exec.toolIdx % toolIds.length];
        const createdAt = new Date(now - exec.hoursAgo * 60 * 60 * 1000);
        return db.toolExecution.create({
          data: {
            toolId, executorId: adminUserId!, status: exec.status,
            input: JSON.stringify({ sample: true, executionSeed: true }),
            output: exec.status === "completed" ? JSON.stringify({ success: true, data: {} }) : null,
            errorMessage: exec.errorMessage, duration: exec.duration, verdict: exec.verdict, verdictReason: exec.verdictReason,
            createdAt, completedAt: ["completed", "failed", "denied", "timeout"].includes(exec.status) ? new Date(createdAt.getTime() + (exec.duration ?? 0)) : null,
          },
        });
      })
    );
    results.push(`Created 50 sample tool executions`);
  } else if (existingExecCount >= 50) {
    results.push(`Tool executions already exist (${existingExecCount} found), skipping`);
  }

  // ─── 10. Seed 8 MetricSeries with MetricPoints ───────────────────
  const existingSeriesCount = await db.metricSeries.count();
  if (existingSeriesCount === 0) {
    const seriesDefs = [
      { name: "gateway.deny_rate", description: "Percentage of tool executions denied by policy engine", category: "security", unit: "percent", labels: JSON.stringify({}) },
      { name: "gateway.execution_throughput", description: "Number of tool executions per minute", category: "operational", unit: "count", labels: JSON.stringify({}) },
      { name: "business.cost_per_flow", description: "Average cost per automated flow execution", category: "business", unit: "usd", labels: JSON.stringify({}) },
      { name: "gateway.avg_latency", description: "Average gateway latency in milliseconds", category: "operational", unit: "ms", labels: JSON.stringify({}) },
      { name: "security.critical_alerts", description: "Number of critical security alerts in the last hour", category: "security", unit: "count", labels: JSON.stringify({}) },
      { name: "resilience.error_rate", description: "Error rate across all tool executions", category: "resilience", unit: "percent", labels: JSON.stringify({}) },
      { name: "business.approval_time", description: "Average time to approve HITL requests in minutes", category: "business", unit: "ms", labels: JSON.stringify({}) },
      { name: "gateway.conditional_verdicts", description: "Rate of conditional verdicts requiring approval", category: "operational", unit: "percent", labels: JSON.stringify({}) },
    ];
    const now = Date.now();
    for (const sd of seriesDefs) {
      const series = await db.metricSeries.create({ data: sd });
      const points = [];
      for (let h = 0; h < 24; h++) {
        let value: number;
        switch (sd.unit) {
          case "percent": value = Math.round((Math.random() * 5 + 0.5) * 100) / 100; break;
          case "ms": value = Math.round(Math.random() * 100 + 20); break;
          case "usd": value = Math.round((Math.random() * 0.5 + 0.05) * 1000) / 1000; break;
          default: value = Math.round(Math.random() * 50 + 5); break;
        }
        points.push({ seriesId: series.id, value, labels: JSON.stringify({ hour: `${h.toString().padStart(2, "0")}:00` }), timestamp: new Date(now - (23 - h) * 60 * 60 * 1000) });
      }
      await db.metricPoint.createMany({ data: points });
    }
    results.push(`Created 8 metric series with 24 data points each (192 total points)`);
  } else {
    results.push(`Metric series already exist (${existingSeriesCount} found), skipping`);
  }

  return results;
}
