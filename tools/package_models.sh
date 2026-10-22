#!/usr/bin/env bash
# Copy the finished deliverables into models/<Name>/ and split every file >= 95 MiB into 90 MiB parts (GitHub's per-file limit is 100 MiB).
# usage: package_models.sh <deliver_dir> <models_dir>      (deliver_dir/<tag>/{<Name>_rigged.blend,<Name>.fbx,<Name>.glb,<Name>_check.mp4,textures/})
set -e
D=$1; M=$2
declare -A P=( [turbo]=Oliver_Turbo_A_Pose [cowboy]=Oliver_Cowboy_Tears_A_Pose [alone]=Oliver_Alone_In_A_Crowd_A_Pose [gray]=Oliver_Gray_Suit_A_Pose )
for t in turbo cowboy alone gray; do
  n=${P[$t]}; mkdir -p "$M/$n/textures"
  for f in "${n}_rigged.blend" "${n}.fbx" "${n}.glb" "${n}_check.mp4"; do
    cp "$D/$t/$f" "$M/$n/$f"
  done
  cp "$D/$t/textures/"* "$M/$n/textures/"
  for f in "$M/$n/"*.blend "$M/$n/"*.fbx "$M/$n/"*.glb "$M/$n/textures/"*; do
    [ -f "$f" ] || continue
    if [ "$(stat -c %s "$f")" -ge $((95*1024*1024)) ]; then
      (cd "$(dirname "$f")" && sha256sum "$(basename "$f")" > "$(basename "$f").sha256" && split -b 90M -d -a 2 "$(basename "$f")" "$(basename "$f").part-" && rm "$(basename "$f")")
      echo "split $f"
    fi
  done
done
