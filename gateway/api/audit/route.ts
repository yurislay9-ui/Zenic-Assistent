import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import type { AuditQuery, PaginatedResponse } from "@/lib/mcp-gateway/types";

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);

    const query: AuditQuery = {
      actorId: searchParams.get("actorId") || undefined,
      action: searchParams.get("action") || undefined,
      resource: searchParams.get("resource") || undefined,
      severity: (searchParams.get("severity") as AuditQuery["severity"]) || undefined,
      outcome: (searchParams.get("outcome") as AuditQuery["outcome"]) || undefined,
      startDate: searchParams.get("startDate") || undefined,
      endDate: searchParams.get("endDate") || undefined,
      search: searchParams.get("search") || undefined,
      page: Math.max(1, Number(searchParams.get("page")) || 1),
      pageSize: Math.min(100, Math.max(1, Number(searchParams.get("pageSize")) || 20)),
    };

    // Build where clause
    const where: {
      actorId?: string;
      action?: { contains: string };
      resource?: string;
      severity?: string;
      outcome?: string;
      createdAt?: { gte?: Date; lte?: Date };
      OR?: Array<Record<string, unknown>>;
    } = {};

    if (query.actorId) where.actorId = query.actorId;
    if (query.action) where.action = { contains: query.action };
    if (query.resource) where.resource = query.resource;
    if (query.severity) where.severity = query.severity;
    if (query.outcome) where.outcome = query.outcome;

    if (query.startDate || query.endDate) {
      where.createdAt = {};
      if (query.startDate) where.createdAt.gte = new Date(query.startDate);
      if (query.endDate) where.createdAt.lte = new Date(query.endDate);
    }

    if (query.search) {
      where.OR = [
        { action: { contains: query.search } },
        { resource: { contains: query.search } },
        { resourceName: { contains: query.search } },
        { actorId: { contains: query.search } },
        { details: { contains: query.search } },
      ];
    }

    const page = query.page ?? 1;
    const pageSize = query.pageSize ?? 20;

    const [logs, total] = await Promise.all([
      db.auditLog.findMany({
        where,
        orderBy: { createdAt: "desc" },
        skip: (page - 1) * pageSize,
        take: pageSize,
      }),
      db.auditLog.count({ where }),
    ]);

    // Parse JSON fields
    const data = logs.map((log) => ({
      ...log,
      details: safeJsonParse(log.details),
      tags: safeJsonParse(log.tags),
    }));

    const response: PaginatedResponse<typeof data[number]> = {
      success: true,
      data,
      total,
      page,
      pageSize,
      totalPages: Math.ceil(total / pageSize),
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error("[Audit GET]", error);
    return NextResponse.json(
      { success: false, error: "Failed to fetch audit logs", code: "INTERNAL_ERROR" },
      { status: 500 }
    );
  }
}

function safeJsonParse(str: string): unknown {
  try {
    return JSON.parse(str);
  } catch {
    return str;
  }
}
