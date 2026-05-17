import { PrismaClient } from '@prisma/client'

const globalForPrisma = globalThis as unknown as {
  prisma: PrismaClient | undefined
}

/**
 * Crea una instancia de PrismaClient con configuración por entorno.
 * - Desarrollo: log query + warn + error (debugging)
 * - Producción: solo warn + error (rendimiento, INVARIANT 3)
 */
function createPrismaClient(): PrismaClient {
  const isDev = process.env.NODE_ENV !== 'production'

  try {
    return new PrismaClient({
      log: isDev
        ? ['query', 'warn', 'error']
        : ['warn', 'error'],
    })
  } catch (error) {
    // Error descriptivo — si el schema no fue generado, guiar al desarrollador
    const message = error instanceof Error ? error.message : String(error)
    if (message.includes('Could not find')) {
      throw new Error(
        '[Zenic DB] Prisma Client no generado. Ejecuta: npx prisma generate'
      )
    }
    throw new Error(`[Zenic DB] Error creando PrismaClient: ${message}`)
  }
}

/**
 * En desarrollo, reutiliza la instancia global para evitar
 * conexiones duplicadas durante HMR (Hot Module Replacement).
 * El hack anterior ('apiCredential' in prisma) fue eliminado —
 * si el schema cambia, ejecuta `npx prisma generate` y reinicia.
 */
export const db = globalForPrisma.prisma ?? createPrismaClient()

if (process.env.NODE_ENV !== 'production') {
  globalForPrisma.prisma = db
}

/**
 * Graceful shutdown — cierra la conexión SQLite correctamente.
 * Previene corrupción de WAL en entornos con recursos limitados (INVARIANT 3).
 */
if (typeof process !== 'undefined' && typeof process.on === 'function') {
  const shutdown = async () => {
    try {
      await db.$disconnect()
    } catch {
      // Silenciar — el proceso ya está saliendo
    }
    process.exit(0)
  }

  process.on('SIGINT', shutdown)
  process.on('SIGTERM', shutdown)
}
