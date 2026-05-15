import { NextResponse } from "next/server";
import { getDashboardMetrics, getActivityFeed } from "@/lib/mcp-gateway/services/metrics-service";
import type { DashboardMetrics, ActivityItem } from "@/lib/mcp-gateway/types";

export async function GET() {
  try {
    const [metrics, activity] = await Promise.all([
      getDashboardMetrics(),
      getActivityFeed(20),
    ]);

    return NextResponse.json({
      success: true,
      data: {
        metrics: metrics as DashboardMetrics,
        activity: activity as ActivityItem[],
      },
    });
  } catch (error) {
    console.error("[Dashboard Metrics GET]", error);
    return NextResponse.json(
      { success: false, error: "Failed to fetch dashboard metrics", code: "INTERNAL_ERROR" },
      { status: 500 }
    );
  }
}
