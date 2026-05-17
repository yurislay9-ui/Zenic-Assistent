// Zenic-Agents v3.0 — Prisma Seed Script
// Ejecutar con: npx tsx prisma/seed.ts
//
// Pobla la base de datos con datos iniciales necesarios para el dashboard.
// INVARIANTE: Este sistema es para VENDEDORES, no gestores.

import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

async function main() {
  console.log("🌱 Iniciando seed de Zenic-Agents v3.0...");

  // ─── 1. Roles del Sistema ──────────────────────────────────────────
  const roles = [
    {
      name: "seller",
      displayName: "Vendedor",
      description: "Vendedor local que maneja inventario y herramientas MCP",
      color: "#10b981",
      isSystem: true,
      priority: 10,
    },
    {
      name: "admin",
      displayName: "Administrador",
      description: "Administrador del sistema con acceso completo",
      color: "#ef4444",
      isSystem: true,
      priority: 100,
    },
  ];

  for (const role of roles) {
    await prisma.role.upsert({
      where: { name: role.name },
      update: {},
      create: role,
    });
  }
  console.log("  ✓ Roles creados: seller, admin");

  // ─── 2. Permisos Base ──────────────────────────────────────────────
  const permissions = [
    { name: "tool:execute", resource: "tool", action: "execute", displayName: "Ejecutar Herramienta", description: "Ejecutar herramientas MCP registradas" },
    { name: "tool:read", resource: "tool", action: "read", displayName: "Ver Herramientas", description: "Consultar herramientas disponibles" },
    { name: "audit:read", resource: "audit", action: "read", displayName: "Ver Auditoría", description: "Consultar registros de auditoría" },
    { name: "policy:read", resource: "policy", action: "read", displayName: "Ver Políticas", description: "Consultar políticas del sistema" },
    { name: "policy:write", resource: "policy", action: "write", displayName: "Modificar Políticas", description: "Crear o modificar políticas", isDangerous: true },
    { name: "role:admin", resource: "role", action: "admin", displayName: "Administrar Roles", description: "Gestionar roles y permisos", isDangerous: true },
    { name: "subscription:manage", resource: "subscription", action: "admin", displayName: "Gestionar Suscripción", description: "Administrar suscripción y pagos" },
  ];

  for (const perm of permissions) {
    await prisma.permission.upsert({
      where: { name: perm.name },
      update: {},
      create: perm,
    });
  }
  console.log("  ✓ Permisos creados: 7 permisos base");

  // ─── 3. Asignar permisos al rol seller ──────────────────────────────
  const sellerRole = await prisma.role.findUnique({ where: { name: "seller" } });
  const sellerPerms = ["tool:execute", "tool:read", "audit:read", "policy:read", "subscription:manage"];

  if (sellerRole) {
    for (const permName of sellerPerms) {
      const perm = await prisma.permission.findUnique({ where: { name: permName } });
      if (perm) {
        await prisma.rolePermission.upsert({
          where: {
            roleId_permissionId: { roleId: sellerRole.id, permissionId: perm.id },
          },
          update: {},
          create: { roleId: sellerRole.id, permissionId: perm.id },
        });
      }
    }
  }
  console.log("  ✓ Permisos asignados al rol seller");

  // ─── 4. Asignar TODOS los permisos al rol admin ──────────────────────
  const adminRole = await prisma.role.findUnique({ where: { name: "admin" } });

  if (adminRole) {
    const allPerms = await prisma.permission.findMany();
    for (const perm of allPerms) {
      await prisma.rolePermission.upsert({
        where: {
          roleId_permissionId: { roleId: adminRole.id, permissionId: perm.id },
        },
        update: {},
        create: { roleId: adminRole.id, permissionId: perm.id },
      });
    }
  }
  console.log("  ✓ Todos los permisos asignados al rol admin");

  // ─── 5. Políticas de Acceso Base ────────────────────────────────────
  // DENY es absoluto — la topología DAG es inmutable.
  const policies = [
    {
      name: "deny-dangerous-without-approval",
      description: "Denegar acciones peligrosas sin aprobación HITL",
      type: "conditional",
      priority: 1000,
      isEnabled: true,
      conditions: JSON.stringify([{ field: "isDangerous", operator: "eq", value: true }]),
      effect: "require_approval",
    },
    {
      name: "allow-standard-tools",
      description: "Permitir herramientas estándar para vendedores",
      type: "allow",
      priority: 100,
      isEnabled: true,
      conditions: JSON.stringify([{ field: "riskLevel", operator: "in", value: ["low", "medium"] }]),
      effect: "allow",
    },
    {
      name: "deny-critical-tools",
      description: "Denegar herramientas críticas — requiere aprobación explícita",
      type: "deny",
      priority: 2000,
      isEnabled: true,
      conditions: JSON.stringify([{ field: "riskLevel", operator: "eq", value: "critical" }]),
      effect: "deny",
    },
  ];

  for (const policy of policies) {
    await prisma.accessPolicy.upsert({
      where: { name: policy.name },
      update: {},
      create: policy,
    });
  }
  console.log("  ✓ Políticas de acceso creadas: deny-dangerous-without-approval, allow-standard-tools, deny-critical-tools");

  console.log("🌱 Seed completado exitosamente.");
}

main()
  .catch((e) => {
    console.error("❌ Error durante seed:", e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
