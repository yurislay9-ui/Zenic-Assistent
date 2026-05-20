import { PrismaClient } from '@prisma/client'

/**
 * #56 Fix: Optimized Prisma Client Configuration
 * 
 * Previous issues:
 * 1. log: ['query'] was ALWAYS on — massive overhead in production
 * 2. No WAL mode — readers block writers and vice versa
 * 3. No busy_timeout — SQLITE_BUSY fails immediately under load
 * 4. No retry logic — transient SQLITE_BUSY errors kill the request
 * 
 * Fixes applied:
 * 1. Conditional logging — only in development, only 'query' + 'error'
 * 2. WAL mode via $queryRaw on first connection (readers don't block writers)
 * 3. busy_timeout = 5000ms — SQLite retries internally before giving up
 * 4. Retry wrapper with exponential backoff for SQLITE_BUSY errors
 */

const globalForPrisma = globalThis as unknown as {
  prisma: PrismaClient | undefined
  walConfigured: boolean | undefined
}

// Conditional logging: queries only in development
const logConfig = process.env.NODE_ENV === 'development'
  ? ['query', 'error', 'warn'] as const
  : ['error', 'warn'] as const

export const db =
  globalForPrisma.prisma ??
  new PrismaClient({
    log: logConfig,
  })

if (process.env.NODE_ENV !== 'production') globalForPrisma.prisma = db

// ===== #56 Fix: Configure SQLite WAL mode + busy_timeout =====
// WAL mode allows concurrent readers while a writer is active
// busy_timeout tells SQLite to retry instead of failing immediately

async function configureSQLitePerformance() {
  if (globalForPrisma.walConfigured) return

  try {
    // #56 Fix: Use $queryRaw for all PRAGMAs since Prisma's SQLite driver
    // doesn't distinguish between PRAGMAs that return results vs those that don't.
    // We simply ignore the return values for non-query PRAGMAs.

    // Enable WAL mode — readers never block writers and vice versa
    await db.$queryRaw`PRAGMA journal_mode=WAL`

    // busy_timeout = 5 seconds — SQLite retries internally on lock contention
    await db.$queryRaw`PRAGMA busy_timeout=5000`

    // synchronous=NORMAL — faster writes, still safe with WAL
    await db.$queryRaw`PRAGMA synchronous=NORMAL`

    // cache_size = -64000 — 64MB cache (default is 2MB)
    await db.$queryRaw`PRAGMA cache_size=-64000`

    // temp_store=MEMORY — temp tables/indices in RAM
    await db.$queryRaw`PRAGMA temp_store=MEMORY`

    globalForPrisma.walConfigured = true
    console.log('[DB] SQLite performance configured: WAL + busy_timeout=5000ms + sync=NORMAL + cache=64MB')
  } catch (err) {
    console.warn('[DB] SQLite performance configuration failed (non-fatal):', err)
  }
}

// Configure on first connection
configureSQLitePerformance().catch(() => {})

// ===== #56 Fix: Retry wrapper with exponential backoff =====
// For SQLITE_BUSY errors that still happen after busy_timeout

const MAX_RETRIES = 3
const BASE_DELAY_MS = 100

function isBusyError(error: unknown): boolean {
  if (error instanceof Error) {
    const msg = error.message.toLowerCase()
    // SQLITE_BUSY = 5, SQLITE_BUSY_SNAPSHOT = 17
    return msg.includes('sqlite_busy') ||
           msg.includes('database is locked') ||
           msg.includes('sql_busy') ||
           msg.includes('unique constraint') // sometimes contention manifests as this
  }
  return false
}

/**
 * Execute a DB operation with automatic retry on SQLITE_BUSY.
 * Uses exponential backoff: 100ms, 200ms, 400ms.
 * 
 * Usage:
 *   const result = await withRetry(() => db.user.findMany())
 */
export async function withRetry<T>(
  operation: () => Promise<T>,
  maxRetries: number = MAX_RETRIES
): Promise<T> {
  let lastError: unknown

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await operation()
    } catch (error) {
      lastError = error

      if (!isBusyError(error) || attempt === maxRetries) {
        throw error
      }

      const delay = BASE_DELAY_MS * Math.pow(2, attempt)
      console.warn(`[DB] SQLITE_BUSY retry ${attempt + 1}/${maxRetries} (waiting ${delay}ms)`)
      await new Promise(resolve => setTimeout(resolve, delay))
    }
  }

  throw lastError
}

/**
 * Batch write — queue multiple writes and execute them in a transaction.
 * Reduces SQLITE_BUSY contention by grouping writes together.
 * 
 * Usage:
 *   await batchWrite([
 *     () => db.approvalAction.create({ data: ... }),
 *     () => db.approvalRequest.update({ where: ..., data: ... }),
 *   ])
 */
export async function batchWrite<T>(
  operations: Array<() => Promise<T>>
): Promise<T[]> {
  return withRetry(async () => {
    return db.$transaction(operations.map(op => op()))
  })
}
