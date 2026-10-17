#!/usr/bin/env bash
# Rebuild everything the Reforma scenarios need, from the OSM extract and the counts.
#   bash scripts/build_network.sh            (from the repo root)
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh
# synthetic counts only while the real video counts are not there (they would be overwritten)
if [ ! -f env/conteos/pico.csv ] || grep -q SINTETICO env/conteos/pico.csv; then
  python -m env.synthetic_counts # env/conteos/{pico,mediodia}.csv
fi
python -m env.build_network      # env/net/*.net.xml + fixed/actuated programs + tls_names.json
python -m env.demand --static    # env/routes/*.rou.xml (seed 0, for sumo-gui / netedit)
rm -rf env/routes/cache          # generated routes are re-created on demand
