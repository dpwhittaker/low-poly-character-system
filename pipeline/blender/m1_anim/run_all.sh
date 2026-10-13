#!/usr/bin/env bash
# P6 animation pipeline, end to end (see README.md). Run from anywhere.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../../.." && pwd)"
blender="${BLENDER:-$HOME/opt/blender-5.2.2-linux-x64/blender}"
lease="${GPU_LEASE:-$HOME/.local/bin/gpu-lease}"
py="${PY:-$HOME/ml-env/bin/python}"

"$py" -I "$here/fetch_sources.py"
"$blender" -b --python "$here/10_retarget.py" -- "$@"
"$lease" run m1-anim -- "$blender" -b --python "$here/20_render.py" -- --tile 260x480 --samples 24
"$lease" run m1-anim -- "$blender" -b --python "$here/22_closeups.py" -- \
  idle__cmu:40 walk__cmu:10 wave__cmu:5 sit__m2m:20 arms_up__cmu:110
"$lease" run m1-anim -- "$blender" -b --python "$here/preview.py" -- "$here/_work/frames" \
  refpose:m2m:m2m/human-base-animations.glb@Idle_A refpose:kaykit:kaykit/Rogue.glb@Idle refpose:cmu:113_21
"$py" -I "$here/21_compose.py"
"$blender" -b --python "$here/30_export.py"
cd "$repo" && node "$here/check_glb.mjs"
