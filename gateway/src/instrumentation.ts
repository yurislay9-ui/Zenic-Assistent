/**
 * FASE 1.5: Next.js Instrumentation Hook
 * 
 * This file runs once when the Next.js server starts.
 * We use it to register the GracefulShutdown signal handlers
 * which protect SQLite from corruption during OOM kills.
 * 
 * The instrumentation hook is supported natively in Next.js 14+.
 * See: https://nextjs.org/docs/app/building-your-application/optimizing/instrumentation
 */

export async function register() {
  // Only run on the server (not in edge runtime or browser)
  if (process.env.NEXT_RUNTIME === 'edge') {
    return
  }

  try {
    // Dynamic imports to avoid bundling issues in edge runtime
    const { GracefulShutdown, setGracefulShutdown } = await import('@/lib/graceful-shutdown')
    const { governor } = await import('@/lib/resource-governor')
    const { writeQueue } = await import('@/lib/write-queue')
    const { db } = await import('@/lib/db')

    // Create the shutdown handler with all dependencies
    const shutdown = new GracefulShutdown({
      governor,
      writeQueue,
      db,
    })

    // Store globally for access from health endpoint and middleware
    setGracefulShutdown(shutdown)

    // Register signal handlers for graceful shutdown
    // These fire when Kubernetes/Docker sends SIGTERM or user hits Ctrl+C
    process.on('SIGTERM', () => shutdown.handleSignal('SIGTERM'))
    process.on('SIGINT', () => shutdown.handleSignal('SIGINT'))

    console.warn('[Instrumentation] Graceful shutdown handlers registered (SIGTERM, SIGINT)')
  } catch (error) {
    console.warn('[Instrumentation] Failed to register graceful shutdown handlers:', error)
  }
}
