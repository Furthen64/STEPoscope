#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

INPUT="examples/stepAP203/slot1.STEP"
if (( $# > 0 )) && [[ "$1" != -* ]]; then
    INPUT="$1"
    shift
fi

OUTPUT_DIR="${HEADLESS_OUT:-temp/headless_once}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$PROJECT_DIR/.cache/uv}"

echo "Rendering: $INPUT"
echo "Output:    $OUTPUT_DIR"
exec uv run python -m step_explorer render "$INPUT" --out "$OUTPUT_DIR" "$@"
