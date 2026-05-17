// ─── Zenic-Agents v3 — Users List (Refactorizado FASE 9) ─────────────
// CAMBIOS:
// - Autenticación obligatoria (requireAuthAndPermission con user:admin)
// - No expone emails ni lastLogin (data minimization)
// - Keyset pagination para eficiencia con SQLite

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { requireAuthAndPermission } from "@/lib/rbac-auth";

export async function GET(request: NextRequest) {
  // ─── Auth + Permission Check ──────────────────────────────────────
  const authResult = await requireAuthAndPermission(request, "user", "admin");
  if (authResult instanceof NextResponse) return authResult;

  try {
    const { searchParams } = new URL(request.url);
    const pageSize = Math.min(50, Math.max(1, Number(searchParams.get("pageSize")) || 20));
    const cursor = searchParams.get("cursor") || undefined;

    const where: { id?: { gt: string } } = {};
    if (cursor) {
      where.id = { gt: cursor };
    }

    const users = await db.user.findMany({
      where,
      include: {
        roles: {
          include: {
            role: true,
          },
        },
      },
      orderBy: cursor ? { id: "asc" } : { name: "asc" },
      take: pageSize + 1,
    });

    const hasNextPage = users.length > pageSize;
    const data = hasNextPage ? users.slice(0, pageSize) : users;
    const nextCursor = hasNextPage ? data[data.length - 1].id : null;

    // Data minimization: solo campos necesarios
    const sanitizedData = data.map((user) => ({
      id: user.id,
      name: user.name,
      avatar: user.avatar,
      status: user.status,
      roles: user.roles.map((ur) => ({
        id: ur.role.id,
        name: ur.role.name,
        displayName: ur.role.displayName,
        color: ur.role.color,
      })),
    }));

    return NextResponse.json({
      success: true,
      data: sanitizedData,
      pageSize,
      nextCursor,
      hasMore: hasNextPage,
    });
  } catch (error) {
    console.error("[Users GET]", error);
    return NextResponse.json(
      { success: false, error: "Error al obtener usuarios", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
