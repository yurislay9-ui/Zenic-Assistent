#!/usr/bin/env bash
# =============================================================================
# Prisma Schema Merge Script
# Concatenates schema_parts/ into a single schema.prisma for Prisma CLI
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARTS_DIR="$SCRIPT_DIR/schema_parts"
OUTPUT="$SCRIPT_DIR/schema.prisma"

echo "🔧 Merging Prisma schema parts..."

# Start fresh
> "$OUTPUT"

# Concatenate in order (sorted by filename — _header first, then phase1-6)
for part in "$PARTS_DIR"/_header.prisma "$PARTS_DIR"/_phase*.prisma; do
    if [ -f "$part" ]; then
        echo "" >> "$OUTPUT"
        cat "$part" >> "$OUTPUT"
        echo "  ✓ $(basename "$part")"
    fi
done

# Format with Prisma
cd "$SCRIPT_DIR"
npx prisma format 2>/dev/null || echo "  ⚠ prisma format skipped (npx not available)"

echo "✅ Merged schema.prisma generated ($OUTPUT)"
