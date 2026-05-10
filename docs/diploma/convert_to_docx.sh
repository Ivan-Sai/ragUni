#!/usr/bin/env bash
# Конвертація diploma.md → diploma.docx через Pandoc.
#
# Передумови:
#   1. Pandoc встановлений (https://pandoc.org/installing.html)
#   2. reference.docx підготовлений (див. README.md)
#   3. PNG-діаграми згенеровані з .mmd файлів у diagrams/ (див. README.md)
#
# Виконання:
#   bash convert_to_docx.sh
#
# Результат: diploma.docx у поточній директорії.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v pandoc >/dev/null 2>&1; then
    echo "ERROR: pandoc is not installed."
    echo "Download from: https://pandoc.org/installing.html"
    exit 1
fi

REFERENCE_FLAG=""
if [[ -f reference.docx ]]; then
    REFERENCE_FLAG="--reference-doc=reference.docx"
    echo "Using reference.docx for styling."
else
    echo "WARNING: reference.docx not found — using Pandoc defaults."
    echo "         See README.md for instructions on creating reference.docx."
fi

pandoc diploma.md \
    -o diploma.docx \
    --from=markdown+raw_html+pipe_tables+grid_tables+fenced_code_blocks \
    --to=docx \
    $REFERENCE_FLAG \
    --standalone \
    --top-level-division=section

echo
echo "Wrote diploma.docx"
echo
echo "Next steps (manual, in Word):"
echo "  1. Insert title page from the faculty template."
echo "  2. Insert Table of Contents (References → Table of Contents → Automatic 1)."
echo "  3. Replace [Рисунок ...] placeholders with PNG images from diagrams/."
echo "  4. Verify page numbering (title page must NOT be numbered)."
echo "  5. Fill in the statistics in the Реферат section: pages, figures, sources, tables, додатки."
echo "  6. Run spell check (Review → Spelling & Grammar)."
echo "  7. Final plagiarism check (faculty's recommended system)."
