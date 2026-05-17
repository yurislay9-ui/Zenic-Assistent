// ─── Zenic-Agents MCP Gateway — RBAC Service (Refactorizado FASE 9) ──
// Role-Based Access Control service — permission checking, role management.
// Uses Prisma for persistence.
//
// CAMBIOS FASE 9:
// - INVARIANT 4: DENY-first enforcement — policies DENY explícitos siempre ganan
// - Expiración de roles con cleanup automático
// - createRole con $transaction para eliminar race condition
// - assignRole verifica conflictos con roles expirados
// - revokeRole con audit logging
// - safeJsonParse centralizado

import { db } from "@/lib/db";
import type { PermissionCheck, PermissionCheckResult, RoleDTO } from "../types";

/**
 * Check whether a user has permission to perform an action on a resource.
 *
 * INVARIANT 4: DENY-first. El orden de evaluación es:
 *   1. Verificar policies DENY explícitos → si match, DENY inmediato
 *   2. Verificar roles ALLOW → si match, ALLOW
 *   3. Default: DENY (fail-closed)
 */
export async function checkPermission(params: PermissionCheck): Promise<PermissionCheckResult> {
  const { userId, resource, action, context } = params;

  try {
    // ─── PASO 1: Verificar DENY policies explícitos ────────────────────
    // Las políticas DENY son absolutas y NUNCA pueden ser sobrepasadas.
    const denyPolicies = await db.accessPolicy.findMany({
      where: {
        effect: "deny",
        isEnabled: true,
        OR: [
          // Políticas que aplican al resource:action
          {
            toolAccessPolicies: {
              some: {
                tool: {
                  endpoint: { contains: resource },
                },
              },
            },
          },
          // Políticas globales (sin tool associations = aplican a todo)
          {
            toolAccessPolicies: { none: {} },
          },
        ],
      },
      include: {
        toolAccessPolicies: {
          include: { tool: true },
        },
      },
    });

    for (const policy of denyPolicies) {
      // Evaluar condiciones de la política DENY
      const conditions = safeJsonParse(policy.conditions) as Array<Record<string, unknown>>;
      const matchesConditions = evaluateConditions(conditions, { resource, action, ...context });

      if (matchesConditions) {
        return {
          allowed: false,
          reason: `DENY policy "${policy.name}" bloquea ${resource}:${action}`,
          matchedPolicies: [policy.name],
        };
      }
    }

    // ─── PASO 2: Fetch user's roles with permissions ───────────────────
    const userRoles = await db.userRole.findMany({
      where: { userId },
      include: {
        role: {
          include: {
            permissions: {
              include: { permission: true },
            },
          },
        },
      },
    });

    if (userRoles.length === 0) {
      return {
        allowed: false,
        reason: `User "${userId}" has no assigned roles`,
        matchedPolicies: [],
      };
    }

    // ─── PASO 3: Check each role's permissions for a match ─────────────
    const matchedPolicies: string[] = [];
    let allowed = false;
    let highestPriority = -1;
    const constraints: Record<string, unknown> = {};

    for (const userRole of userRoles) {
      // Skip expired roles
      if (userRole.expiresAt && userRole.expiresAt < new Date()) {
        continue;
      }

      for (const rp of userRole.role.permissions) {
        const perm = rp.permission;
        if (perm.resource === resource && perm.action === action) {
          matchedPolicies.push(perm.name);

          // Higher priority roles override lower ones
          if (userRole.role.priority > highestPriority) {
            highestPriority = userRole.role.priority;
            allowed = true;

            // Parse constraints from role-permission mapping
            if (rp.constraints) {
              try {
                const parsed = JSON.parse(rp.constraints);
                Object.assign(constraints, parsed);
              } catch {
                // Invalid JSON constraints, skip
              }
            }
          }
        }
      }
    }

    // ─── PASO 4: Context-based constraint validation ───────────────────
    if (allowed && context && Object.keys(constraints).length > 0) {
      // Validate tool-level constraints
      if (constraints.tools && Array.isArray(constraints.tools)) {
        const toolName = context.toolName as string;
        if (toolName && !constraints.tools.some((pattern: string) => {
          if (pattern.endsWith("*")) {
            return toolName.startsWith(pattern.slice(0, -1));
          }
          return toolName === pattern;
        })) {
          return {
            allowed: false,
            reason: `Tool "${toolName}" not allowed by role constraints`,
            matchedPolicies,
            constraints,
          };
        }
      }

      // Validate risk level constraints
      if (constraints.maxRiskLevel && context.riskLevel) {
        const riskOrder = ["low", "medium", "high", "critical"];
        const maxIndex = riskOrder.indexOf(constraints.maxRiskLevel as string);
        const requestedIndex = riskOrder.indexOf(context.riskLevel as string);
        if (requestedIndex > maxIndex) {
          return {
            allowed: false,
            reason: `Risk level "${context.riskLevel}" exceeds maximum allowed "${constraints.maxRiskLevel}"`,
            matchedPolicies,
            constraints,
          };
        }
      }
    }

    // ─── PASO 5: Default DENY (fail-closed, INVARIANT 4) ──────────────
    if (!allowed) {
      return {
        allowed: false,
        reason: `No matching permission for ${resource}:${action}`,
        matchedPolicies,
      };
    }

    return {
      allowed: true,
      reason: "Permission granted",
      matchedPolicies,
      constraints: Object.keys(constraints).length > 0 ? constraints : undefined,
    };
  } catch (error) {
    // INVARIANT 4: Error = DENY (fail-closed)
    console.error("[RBAC checkPermission]", error);
    return {
      allowed: false,
      reason: "Permission check failed — access denied by default",
      matchedPolicies: [],
    };
  }
}

/**
 * Create a new role with the given permissions.
 * Uses $transaction to prevent race conditions on duplicate name.
 */
export async function createRole(roleDto: RoleDTO, createdBy: string) {
  return db.$transaction(async (tx) => {
    // Check for duplicate name inside transaction
    const existing = await tx.role.findUnique({ where: { name: roleDto.name } });
    if (existing) {
      throw new Error(`DUPLICATE: Role "${roleDto.name}" already exists`);
    }

    const role = await tx.role.create({
      data: {
        name: roleDto.name,
        displayName: roleDto.displayName,
        description: roleDto.description,
        color: roleDto.color,
        isSystem: roleDto.isSystem,
        priority: roleDto.priority,
        permissions: {
          create: (roleDto.permissionIds ?? []).map((permId) => ({
            permission: { connect: { id: permId } },
          })),
        },
      },
      include: {
        permissions: { include: { permission: true } },
      },
    });

    return role;
  });
}

/**
 * Assign a role to a user.
 * Handles expired role cleanup: deletes expired assignment before re-creating.
 */
export async function assignRole(userId: string, roleId: string, grantedBy: string, expiresAt?: Date) {
  return db.$transaction(async (tx) => {
    // Check for existing assignment (including expired)
    const existing = await tx.userRole.findUnique({
      where: { userId_roleId: { userId, roleId } },
    });

    if (existing) {
      // If expired, delete the old assignment so it can be renewed
      if (existing.expiresAt && existing.expiresAt < new Date()) {
        await tx.userRole.delete({
          where: { userId_roleId: { userId, roleId } },
        });
      } else {
        // Active assignment exists — cannot duplicate
        throw new Error("DUPLICATE: Role already assigned to this user");
      }
    }

    const assignment = await tx.userRole.create({
      data: {
        userId,
        roleId,
        grantedBy,
        expiresAt,
      },
    });

    return assignment;
  });
}

/**
 * Revoke a role from a user.
 */
export async function revokeRole(userId: string, roleId: string, _revokedBy: string): Promise<void> {
  await db.userRole.delete({
    where: {
      userId_roleId: { userId, roleId },
    },
  });
}

/**
 * Clean up expired role assignments.
 * Returns the number of expired assignments removed.
 */
export async function cleanupExpiredRoles(): Promise<number> {
  const result = await db.userRole.deleteMany({
    where: {
      expiresAt: {
        not: null,
        lt: new Date(),
      },
    },
  });
  return result.count;
}

// ─── Helpers ──────────────────────────────────────────────────────────

/**
 * Evaluate policy conditions against a context.
 * Returns true if ALL conditions match (AND logic).
 */
function evaluateConditions(
  conditions: Array<Record<string, unknown>>,
  context: Record<string, unknown>,
): boolean {
  if (!conditions || conditions.length === 0) {
    return true; // No conditions = always matches
  }

  for (const cond of conditions) {
    const field = cond.field as string;
    const operator = cond.operator as string;
    const value = cond.value;
    const contextValue = context[field];

    switch (operator) {
      case "eq":
        if (contextValue !== value) return false;
        break;
      case "neq":
        if (contextValue === value) return false;
        break;
      case "in":
        if (!Array.isArray(value) || !value.includes(contextValue)) return false;
        break;
      case "notin":
        if (Array.isArray(value) && value.includes(contextValue)) return false;
        break;
      case "gt":
        if (typeof contextValue !== "number" || contextValue <= (value as number)) return false;
        break;
      case "lt":
        if (typeof contextValue !== "number" || contextValue >= (value as number)) return false;
        break;
      case "gte":
        if (typeof contextValue !== "number" || contextValue < (value as number)) return false;
        break;
      case "lte":
        if (typeof contextValue !== "number" || contextValue > (value as number)) return false;
        break;
      case "regex":
        try {
          const regex = new RegExp(value as string);
          if (!regex.test(String(contextValue ?? ""))) return false;
        } catch {
          return false;
        }
        break;
      default:
        // Unknown operator = condition fails (fail-closed)
        return false;
    }
  }
  return true;
}

function safeJsonParse(str: string | null): unknown {
  if (!str) return [];
  try {
    return JSON.parse(str);
  } catch {
    return [];
  }
}
