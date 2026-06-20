#!/usr/bin/env bash
# Convert a markdown file to PDF with embedded images.
#
# Uses pandoc for markdown→HTML and weasyprint for HTML→PDF.
# On macOS, handles the pango library path issue automatically.
#
# Usage:
#   scripts/md-to-pdf.sh <input.md> [output.pdf]
#   scripts/md-to-pdf.sh docs/interview-prep-librarian.md
#   scripts/md-to-pdf.sh docs/interview-prep-librarian.md out/report.pdf
#
# If output.pdf is omitted, the output is placed alongside the input
# with the same basename and a .pdf extension.

set -euo pipefail

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; NC=$'\033[0m'

# --- Parse args ---------------------------------------------------------------

INPUT="$1"
OUTPUT="${2:-${INPUT%.md}.pdf}"

if [[ ! -f "$INPUT" ]]; then
  printf '%s[err]%s  input file not found: %s\n' "$RED" "$NC" "$INPUT" >&2
  exit 1
fi

INPUT_DIR="$(cd "$(dirname "$INPUT")" && pwd)"
INPUT_NAME="$(basename "$INPUT")"
HTML_TEMP="$(mktemp /tmp/md-to-pdf.XXXXXX.html)"
OUTPUT_ABS="$(cd "$(dirname "$OUTPUT")" 2>/dev/null && pwd)/$(basename "$OUTPUT")" || OUTPUT_ABS="$OUTPUT"

# --- Preflight ----------------------------------------------------------------

for tool in pandoc python3; do
  command -v "$tool" >/dev/null 2>&1 || {
    printf '%s[err]%s  required tool not found: %s\n' "$RED" "$NC" "$tool" >&2
    exit 2
  }
done

# --- Convert markdown → HTML (pandoc) ----------------------------------------

printf 'Converting %s → HTML...\n' "$INPUT_NAME"

pandoc "$INPUT" -o "$HTML_TEMP" \
  --from markdown \
  --standalone \
  --metadata title="$(basename "$INPUT" .md)" \
  2>&1

# Copy HTML alongside input so weasyprint can resolve relative image paths
HTML_LOCAL="${INPUT_DIR}/.md-to-pdf-temp.html"
cp "$HTML_TEMP" "$HTML_LOCAL"

# --- Convert HTML → PDF (weasyprint) -----------------------------------------

printf 'Rendering PDF...\n'

DYLD_LIBRARY_PATH="${DYLD_LIBRARY_PATH:-}/opt/homebrew/lib:/usr/local/lib" \
  python3 -c "
import sys
from weasyprint import HTML
try:
    HTML('$HTML_LOCAL').write_pdf('$OUTPUT_ABS')
    print('OK')
except Exception as exc:
    print(f'PDF generation failed: {exc}', file=sys.stderr)
    sys.exit(3)
" 2>&1

# --- Cleanup -----------------------------------------------------------------

rm -f "$HTML_LOCAL" "$HTML_TEMP"

if [[ -f "$OUTPUT_ABS" ]]; then
  size=$(ls -lh "$OUTPUT_ABS" | awk '{print $5}')
  printf '%s[ok]%s   %s (%s)\n' "$GREEN" "$NC" "$OUTPUT_ABS" "$size"
else
  printf '%s[err]%s  PDF was not created\n' "$RED" "$NC" >&2
  exit 3
fi
