import { PrismaClient } from '@prisma/client'

const globalForPrisma = globalThis as unknown as {
  prisma: PrismaClient | undefined
}

// Force recreate if the client doesn't have the latest models
// This handles HMR not picking up new Prisma models after schema changes
if (globalForPrisma.prisma) {
  try {
    const hasApiCredential = 'apiCredential' in globalForPrisma.prisma;
    if (!hasApiCredential) {
      try { globalForPrisma.prisma.$disconnect(); } catch { /* ignore */ }
      globalForPrisma.prisma = undefined;
    }
  } catch {
    globalForPrisma.prisma = undefined;
  }
}

export const db =
  globalForPrisma.prisma ??
  new PrismaClient({
    log: ['query'],
  })

if (process.env.NODE_ENV !== 'production') globalForPrisma.prisma = db
