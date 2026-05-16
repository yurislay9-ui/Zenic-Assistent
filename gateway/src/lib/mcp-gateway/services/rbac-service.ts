// ─── Zenic-Agents MCP Gateway — RBAC Service ──────────────────────────
// Role-Based Access Control service — permission checking, role management.
// Uses Prisma for persistence.

import { db } from "@/lib/db";
import type { PermissionCheck, PermissionCheckResult, RoleDTO } from "../types";

/**
 * Check whether a user has permission to perform an action on a resource.
 * Evaluates all roles assigned to the user and checks for matching permissions.
 */
export async function checkPermission(params: PermissionCheck): Promise<PermissionCheckResult> {
  const { userId, resource, action, context } = params;

  try {
    // Fetch user's roles with permissions
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

    // Check each role's permissions for a match
    const matchedPolicies: string[] = [];
    let allowed = false;
    let highestPriority = -1;
    const constraints: Record<string, unknown> = {};

    for (const userRole of userRoles) {
      // Check if any expired
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

    // Context-based constraint validation
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
          allowed = false;
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
          allowed = false;
          return {
            allowed: false,
            reason: `Risk level "${context.riskLevel}" exceeds maximum allowed "${constraints.maxRiskLevel}"`,
            matchedPolicies,
            constraints,
          };
        }
      }
    }

    return {
      allowed,
      reason: allowed ? "Permission granted" : `No matching permission for ${resource}:${action}`,
      matchedPolicies,
      constraints: Object.keys(constraints).length > 0 ? constraints : undefined,
    };
  } catch (error) {
    console.error("[RBAC checkPermission]", error);
    return {
      allowed: false,
      reason: "Permission check failed due to internal error",
      matchedPolicies: [],
    };
  }
}

/**
 * Create a new role with the given permissions.
 */
export async function createRole(roleDto: RoleDTO, createdBy: string) {
  const role = await db.role.create({
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
}

/**
 * Assign a role to a user.
 */
export async function assignRole(userId: string, roleId: string, grantedBy: string, expiresAt?: Date) {
  const assignment = await db.userRole.create({
    data: {
      userId,
      roleId,
      grantedBy,
      expiresAt,
    },
  });

  return assignment;
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
