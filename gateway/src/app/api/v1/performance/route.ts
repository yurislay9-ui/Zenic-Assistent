/**
 * ZENIC-AGENTS v16 - Performance Dashboard API (Phase 4.4)
 *
 * GET /api/v1/performance
 *   Returns comprehensive performance metrics for the dashboard UI.
 *
 * GET /api/v1/performance?alerts=true
 *   Returns active performance alerts.
 *
 * GET /api/v1/performance?timeseries=true
 *   Returns time series data (last 5 minutes).
 */

import { NextRequest, NextResponse } from 'next/server';
import { performanceDashboard } from '@/lib/performance-dashboard';

export async function GET(request: NextRequest) {
  const searchParams = request.searchParams;
  const includeAlerts = searchParams.get('alerts') === 'true';
  const includeTimeSeries = searchParams.get('timeseries') === 'true';

  try {
    const snapshot = performanceDashboard.getSnapshot();

    // Filter response based on query params
    if (includeAlerts) {
      return NextResponse.json({
        alerts: performanceDashboard.getAlerts(),
        timestamp: snapshot.timestamp,
      });
    }

    if (includeTimeSeries) {
      return NextResponse.json({
        timeSeries: snapshot.timeSeries,
        timestamp: snapshot.timestamp,
      });
    }

    // Full snapshot
    return NextResponse.json({
      ...snapshot,
      alerts: performanceDashboard.getAlerts(),
    });
  } catch (error) {
    return NextResponse.json(
      {
        error: 'Performance dashboard unavailable',
        message: error instanceof Error ? error.message : 'Unknown error',
        timestamp: Date.now(),
      },
      { status: 503 }
    );
  }
}
