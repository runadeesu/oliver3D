#!/usr/bin/env bash
# Render the check videos of the delivered .blend files (3 parallel Blender workers per model).
# usage: render_videos.sh <models_dir>   (expects <models_dir>/<Name>/<Name>_rigged.blend; needs setup_env.sh + OLIVER_WORK)
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
export OLIVER_ROOT=$(cd "$HERE/.." && pwd)
M=${1:-$OLIVER_ROOT/models}
declare -A P=( [turbo]=Oliver_Turbo_A_Pose [cowboy]=Oliver_Cowboy_Tears_A_Pose [alone]=Oliver_Alone_In_A_Crowd_A_Pose [gray]=Oliver_Gray_Suit_A_Pose )
for t in turbo cowboy alone gray; do
  rm -rf "$OLIVER_WORK/vid_$t"
  B=$M/${P[$t]}/${P[$t]}_rigged.blend
  for r in "1 212" "213 424" "425 636"; do
    set -- $r
    "$BLENDER" -b "$B" --python "$HERE/oliver_rig/render_video.py" -- $t "$M/${P[$t]}/${P[$t]}_check.mp4" 2 $1 $2 noencode > "$OLIVER_WORK/vid_log_${t}_$1.txt" 2>&1 &
  done
  wait
  bash "$HERE/oliver_rig/encode_video.sh" "$OLIVER_WORK/vid_$t/frames" 2 "$M/${P[$t]}/${P[$t]}_check.mp4"
done
