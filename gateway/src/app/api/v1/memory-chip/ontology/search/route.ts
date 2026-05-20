// ─── GET /api/v1/memory-chip/ontology/search ───────────────────────────
// Search the ontology base for a term.

import { NextRequest, NextResponse } from 'next/server';
import { searchOntologyBase, type OntologySearchResult } from '@/lib/memory-chip';

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const term = searchParams.get('term');

    if (!term || term.trim().length === 0) {
      return NextResponse.json(
        { success: false, error: 'Missing required query parameter: term' },
        { status: 400 },
      );
    }

    const results: OntologySearchResult[] = searchOntologyBase(term.trim());

    return NextResponse.json({
      success: true,
      data: results,
      meta: {
        query: term.trim(),
        result_count: results.length,
        source: 'ontology_base',
      },
    });
  } catch (error) {
    console.error('[memory-chip/ontology/search] Error:', error);
    return NextResponse.json(
      { success: false, error: 'Internal server error' },
      { status: 500 },
    );
  }
}
