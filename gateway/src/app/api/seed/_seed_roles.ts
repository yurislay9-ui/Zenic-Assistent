import { db } from "@/lib/db";

/**
 * Seed admin user, roles, and permissions.
 * Sections 1–3 of the original monolithic seed route.
 */
export async function seedRolesAndPermissions(): Promise<{
  adminUserId: string | undefined;
  results: string[];
}> {
  const results: string[] = [];

  // ─── 1. Seed Admin User ───────────────────────────────────────────
  let adminUser = await db.user.findUnique({ where: { email: "admin@zenic.dev" } });
  if (!adminUser) {
    adminUser = await db.user.create({
      data: {
        email: "admin@zenic.dev",
        name: "Admin User",
        status: "active",
        lastLogin: new Date(),
      },
    });
    results.push("Created admin user (admin@zenic.dev)");
  } else {
    results.push("Admin user already exists, skipping");
  }

  // ─── 2. Seed 4 Roles ─────────────────────────────────────────────
  const roleDefs = [
    { name: "superadmin", displayName: "Super Admin", description: "Full system access — no restrictions", color: "#dc2626", isSystem: true, priority: 100 },
    { name: "admin", displayName: "Admin", description: "Manage tools, policies, and roles", color: "#ea580c", isSystem: true, priority: 80 },
    { name: "operator", displayName: "Operator", description: "Execute tools and monitor system", color: "#0891b2", isSystem: true, priority: 50 },
    { name: "viewer", displayName: "Viewer", description: "Read-only access to tools and audit logs", color: "#6b7280", isSystem: true, priority: 10 },
  ];

  for (const rd of roleDefs) {
    const existing = await db.role.findUnique({ where: { name: rd.name } });
    if (!existing) {
      await db.role.create({ data: rd });
    }
  }
  results.push("Roles ensured (4 roles)");

  // ─── 3. Seed 18 Permissions ──────────────────────────────────────
  const permissionDefs = [
    { name: "tool:read", resource: "tool", action: "read", displayName: "Read Tools", description: "View tool registry and details", isDangerous: false },
    { name: "tool:write", resource: "tool", action: "write", displayName: "Manage Tools", description: "Create, update, and configure tools", isDangerous: false },
    { name: "tool:execute", resource: "tool", action: "execute", displayName: "Execute Tools", description: "Run tool executions through gateway", isDangerous: true },
    { name: "tool:delete", resource: "tool", action: "delete", displayName: "Delete Tools", description: "Remove tools from registry", isDangerous: true },
    { name: "server:read", resource: "server", action: "read", displayName: "Read Servers", description: "View MCP server configurations", isDangerous: false },
    { name: "server:write", resource: "server", action: "write", displayName: "Manage Servers", description: "Configure MCP servers", isDangerous: false },
    { name: "role:read", resource: "role", action: "read", displayName: "Read Roles", description: "View role configurations", isDangerous: false },
    { name: "role:write", resource: "role", action: "write", displayName: "Manage Roles", description: "Create and modify roles", isDangerous: true },
    { name: "role:delete", resource: "role", action: "delete", displayName: "Delete Roles", description: "Remove roles from system", isDangerous: true },
    { name: "policy:read", resource: "policy", action: "read", displayName: "Read Policies", description: "View access policies", isDangerous: false },
    { name: "policy:write", resource: "policy", action: "write", displayName: "Manage Policies", description: "Create and modify access policies", isDangerous: true },
    { name: "policy:delete", resource: "policy", action: "delete", displayName: "Delete Policies", description: "Remove access policies", isDangerous: true },
    { name: "audit:read", resource: "audit", action: "read", displayName: "Read Audit Logs", description: "View audit trail", isDangerous: false },
    { name: "audit:export", resource: "audit", action: "export", displayName: "Export Audit Logs", description: "Export audit data", isDangerous: true },
    { name: "execution:read", resource: "execution", action: "read", displayName: "Read Executions", description: "View execution history", isDangerous: false },
    { name: "execution:approve", resource: "execution", action: "approve", displayName: "Approve Executions", description: "Approve pending tool executions", isDangerous: true },
    { name: "dashboard:read", resource: "dashboard", action: "read", displayName: "View Dashboard", description: "Access dashboard metrics", isDangerous: false },
    { name: "user:admin", resource: "user", action: "admin", displayName: "Admin Users", description: "Full user management", isDangerous: true },
  ];

  const existingPermCount = await db.permission.count();
  if (existingPermCount === 0) {
    await db.permission.createMany({ data: permissionDefs });
    results.push(`Created ${permissionDefs.length} permissions`);
  } else {
    results.push(`Permissions already exist (${existingPermCount} found), skipping`);
  }

  return { adminUserId: adminUser?.id, results };
}
