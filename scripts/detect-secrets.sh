#!/bin/bash
# ─── Zenic-Agents — Pre-commit Secret Detection Hook ──────────────
# Scans staged files for hardcoded secret patterns.
# Install: ln -sf ../../scripts/detect-secrets.sh .git/hooks/pre-commit
# Or add to .pre-commit-config.yaml
set -euo pipefail

RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Patterns that indicate hardcoded secrets (SEC-1 through SEC-7)
PATTERNS=(
  "zenic_[a-z_]*_key_[0-9]+"
  "default-signing-key-change-me"
  "default-key"
  "zenic-agents-fernet-salt"
  "zenic-agents-v3-certification-key"
  "REPLACE_WITH_openssl"
  "-----BEGIN (RSA |EC )?PRIVATE KEY-----"
  "sk-[a-zA-Z0-9]{20,}"
  "ghp_[a-zA-Z0-9]{36}"
  "AKIA[0-9A-Z]{16}"
  "xox[bpas]-[0-9a-zA-Z-]+"
)

# File extensions to scan
SCAN_EXTENSIONS=(
  ".ts" ".tsx" ".js" ".jsx" ".py" ".rs" ".json" ".yaml" ".yml" ".toml" ".env"
)

STAGED=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null || echo "")
if [ -z "$STAGED" ]; then
  exit 0
fi

FOUND=0
DETAILS=""

for FILE in "STAGED"; do
  # Check if file extension matches
  EXT="${FILE##*.}"
  MATCH=0
  for SCAN_EXT in "${SCAN_EXTENSIONS[@]}"; do
    if [ ".$EXT" = "$SCAN_EXT" ] || [ "$FILE" = ".env" ] || [[ "$FILE" == *".env"* ]]; then
      MATCH=1
      break
    fi
  done

  if [ "$MATCH" -eq 0 ]; then
    continue
  fi

  # Skip this script itself
  if [[ "$FILE" == *"detect-secrets"* ]]; then
    continue
  fi

  for PATTERN in "${PATTERNS[@]}"; do
    if git diff --cached "$FILE" 2>/dev/null | grep -qE "$PATTERN"; then
      DETAILS="${DETAILS}\n${RED}SECRET DETECTED${NC} in ${YELLOW}${FILE}${NC}: pattern '${PATTERN}'"
      FOUND=1
    fi
  done
done

if [ $FOUND -ne 0 ]; then
  echo ""
  echo -e "${RED}╔══════════════════════════════════════════════════╗${NC}"
  echo -e "${RED}║  COMMIT BLOCKED: Hardcoded secrets detected!     ║${NC}"
  echo -e "${RED}╚══════════════════════════════════════════════════╝${NC}"
  echo ""
  echo -e "$DETAILS"
  echo ""
  echo "To fix:"
  echo "  1. Move secrets to environment variables (.env file)"
  echo "  2. Use process.env.X in TypeScript or os.environ.get('X') in Python"
  echo "  3. Run: bash gateway/scripts/generate-env.sh to generate secure values"
  echo ""
  echo "To bypass (NOT RECOMMENDED): git commit --no-verify"
  exit 1
fi

exit 0
