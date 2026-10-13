#!/usr/bin/env bash
# Rebuild docs/m0/style-frames.png: shoot every style × facets × view in headless Chrome on
# the iGPU (tools/shoot.cjs, dev server must be up), then compose next to the reference.
set -euo pipefail
cd "$(dirname "$0")/.."
S="${TMPDIR:-/tmp}/lpcs-style-sheet"; mkdir -p "$S" docs/m0
J=()
for st in S1 S2 S3; do for sh in flat smooth; do
  J+=("$S/${st}_${sh}_body.png" "style=$st&view=body&shade=$sh&yaw=-28&ui=0")
  J+=("$S/${st}_${sh}_face.png" "style=$st&view=face&shade=$sh&yaw=-20&ui=0")
done; done
node tools/shoot.cjs "${J[@]}" --size=600x900
B1=$(stat -c%s public/m0/S1.glb) B2=$(stat -c%s public/m0/S2.glb) B3=$(stat -c%s public/m0/S3.glb) \
  ~/ml-env/bin/python -I tools/style_sheet_compose.py "$S" docs/m0/style-frames.png public/m0/reference.webp
