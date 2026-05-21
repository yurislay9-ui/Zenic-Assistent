import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';
import bcrypt from 'bcryptjs';
import { generateIdentityToken } from '@/lib/hitl';

/**
 * POST /api/identity/verify
 * 
 * #40 Fix: Identity verification endpoint.
 * The user must re-enter their password before they can approve HITL requests.
 * Returns a short-lived identity token that proves the user verified themselves.
 */
export async function POST(req: NextRequest) {
  try {
    const { email, password } = await req.json();

    if (!email || !password) {
      return NextResponse.json(
        { error: 'Email and password are required for identity verification' },
        { status: 400 }
      );
    }

    // Verify the user's credentials
    const user = await db.user.findUnique({
      where: { email },
    });

    if (!user || !user.isActive || !user.password) {
      return NextResponse.json(
        { error: 'Identity verification failed' },
        { status: 401 }
      );
    }

    const isValid = await bcrypt.compare(password, user.password);
    if (!isValid) {
      // Log failed verification attempt
      console.warn(`[HITL] Failed identity verification for ${email} at ${new Date().toISOString()}`);
      return NextResponse.json(
        { error: 'Identity verification failed — incorrect password' },
        { status: 401 }
      );
    }

    // Generate identity token (valid for 5 minutes)
    const challengeId = `${user.id}:${Date.now()}`;
    const identityToken = generateIdentityToken(user.id, challengeId);

    return NextResponse.json({
      success: true,
      identityToken,
      userId: user.id,
      expiresIn: 300, // seconds
    });
  } catch (error: any) {
    return NextResponse.json(
      { error: error.message },
      { status: 500 }
    );
  }
}
