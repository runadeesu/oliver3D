#!/usr/bin/env bash
# usage: encode_video.sh <frames_dir> <step> <out.mp4>   (frames named fNNNNN.png, rendered every <step>-th frame of a 24 fps animation)
set -e
FR=$1; STEP=$2; OUT=$3
ffmpeg -y -loglevel error -framerate $((24/STEP)) -pattern_type glob -i "$FR/f*.png" -vf "fps=24" -c:v libx264 -pix_fmt yuv420p -crf 20 -preset medium -movflags +faststart "$OUT"
