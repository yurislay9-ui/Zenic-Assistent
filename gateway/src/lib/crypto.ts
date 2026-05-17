// ─── Cifrado AES-256-GCM para credenciales de servicio ───────────────
// SECURITY: Cualquier script XSS puede leer localStorage, pero NO puede
// leer la base de datos ni los env vars del servidor.
// INVARIANT 4 — defensa en profundidad, la regla DENY es absoluta.
//
// Flujo:
//   1. Frontend envia campos en texto plano al API endpoint (HTTPS).
//   2. API endpoint cifra con AES-256-GCM usando ZENIC_ENCRYPTION_KEY.
//   3. Se almacena encryptedData + iv + authTag en SQLite via Prisma.
//   4. Al leer, API descifra y enmascara antes de enviar al frontend.
//   5. localStorage se elimina completamente.

import { createCipheriv, createDecipheriv, randomBytes } from "node:crypto";

const ALGORITHM = "aes-256-gcm";
const IV_LENGTH = 16; // 128 bits para GCM
const AUTH_TAG_LENGTH = 16;

/**
 * Obtiene la clave de cifrado desde la variable de entorno.
 * Falla explícitamente si no está configurada — mejor fallar que silenciar.
 */
function getEncryptionKey(): Buffer {
  const key = process.env.ZENIC_ENCRYPTION_KEY;
  if (!key) {
    throw new Error(
      "[Zenic Crypto] ZENIC_ENCRYPTION_KEY no configurada. " +
      "Genera una con: openssl rand -hex 32"
    );
  }
  if (key.length !== 64) {
    throw new Error(
      "[Zenic Crypto] ZENIC_ENCRYPTION_KEY debe tener exactamente 64 caracteres hex (32 bytes / 256 bits). " +
      `Longitud actual: ${key.length}`
    );
  }
  return Buffer.from(key, "hex");
}

export interface EncryptedPayload {
  encryptedData: string; // hex
  iv: string;            // hex
  authTag: string;       // hex
}

/**
 * Cifra un objeto JavaScript como JSON usando AES-256-GCM.
 * Retorna encryptedData, iv y authTag en formato hex.
 */
export function encrypt(plaintext: Record<string, string>): EncryptedPayload {
  const key = getEncryptionKey();
  const iv = randomBytes(IV_LENGTH);
  const cipher = createCipheriv(ALGORITHM, key, iv, {
    authTagLength: AUTH_TAG_LENGTH,
  });

  const data = JSON.stringify(plaintext);
  const encrypted = Buffer.concat([
    cipher.update(data, "utf8"),
    cipher.final(),
  ]);
  const authTag = cipher.getAuthTag();

  return {
    encryptedData: encrypted.toString("hex"),
    iv: iv.toString("hex"),
    authTag: authTag.toString("hex"),
  };
}

/**
 * Descifra datos AES-256-GCM y retorna el objeto JavaScript parseado.
 * Lanza error si la autenticación falla (datos alterados o clave incorrecta).
 */
export function decrypt(payload: EncryptedPayload): Record<string, string> {
  const key = getEncryptionKey();
  const iv = Buffer.from(payload.iv, "hex");
  const authTag = Buffer.from(payload.authTag, "hex");
  const encryptedData = Buffer.from(payload.encryptedData, "hex");

  const decipher = createDecipheriv(ALGORITHM, key, iv, {
    authTagLength: AUTH_TAG_LENGTH,
  });
  decipher.setAuthTag(authTag);

  const decrypted = Buffer.concat([
    decipher.update(encryptedData),
    decipher.final(),
  ]);

  return JSON.parse(decrypted.toString("utf8"));
}

/**
 * Enmascara valores de un diccionario para envío seguro al frontend.
 * FIX #12: Antes mostraba 3+2 chars para valores >5, exponiendo credenciales cortas.
 * Ahora: valores <=8 se reemplazan completamente; >8 muestra 2+2 con "•••" al medio.
 */
export function maskCredentialFields(
  campos: Record<string, string>
): Record<string, string> {
  const masked: Record<string, string> = {};
  for (const [key, value] of Object.entries(campos)) {
    if (!value || value.length <= 8) {
      masked[key] = "••••••";
    } else {
      masked[key] = `${value.slice(0, 2)}•••${value.slice(-2)}`;
    }
  }
  return masked;
}
