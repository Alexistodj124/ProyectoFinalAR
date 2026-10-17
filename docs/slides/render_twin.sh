#!/bin/bash
# Renderiza el gemelo HTML con Chrome headless: PDF (presentacion.pdf) + PNG por diapositiva + lista de desbordes.
# Uso: bash render_twin.sh <dir_salida_png>
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$HERE/.build/render}"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PROFILE="$(mktemp -d)"
URL="file://$HERE/presentacion_gemelo.html"
mkdir -p "$OUT"
rm -f "$HERE/presentacion.pdf" "$OUT"/slide-*.png

run() { # Chrome headless a veces no termina solo: se le da un tiempo y se mata
  "$CHROME" --headless=new --disable-gpu --no-sandbox --user-data-dir="$PROFILE" --allow-file-access-from-files "$@" &
  local pid=$!
  for _ in $(seq 1 60); do kill -0 $pid 2>/dev/null || break; sleep 1; done
  kill $pid 2>/dev/null; wait $pid 2>/dev/null
}
run --no-pdf-header-footer --print-to-pdf="$HERE/presentacion.pdf" "$URL" >/dev/null 2>&1
run --virtual-time-budget=3000 --dump-dom "$URL#qa" 2>/dev/null > "$OUT/dom.html"
grep -o 'data-overflow="[^"]*"' "$OUT/dom.html" | sed 's/&quot;/"/g'
pdftoppm -png -r 80 "$HERE/presentacion.pdf" "$OUT/slide"
ls "$OUT" | grep -c png
rm -rf "$PROFILE"
