#!/usr/bin/env bash
# Environment bootstrap used while building the deliverables (Linux x64).
# Usage: source tools/setup_env.sh <work_dir>
set -e
WORKDIR=${1:-/tmp/oliver_env}
mkdir -p "$WORKDIR"
if [ ! -x "$WORKDIR/blender/blender" ]; then
  curl -L -o "$WORKDIR/blender.tar.xz" https://download.blender.org/release/Blender4.5/blender-4.5.14-linux-x64.tar.xz
  mkdir -p "$WORKDIR/blender" && tar -xf "$WORKDIR/blender.tar.xz" -C "$WORKDIR/blender" --strip-components=1
fi
# Blender needs libEGL even in background mode (software GL via Mesa is enough)
command -v ldconfig >/dev/null && ldconfig -p | grep -q libEGL.so.1 || \
  apt-get install -y --no-install-recommends libegl1 libgl1 libgl1-mesa-dri libglx-mesa0 libegl-mesa0 libgbm1 libxkbcommon0 libsm6 libxi6 libxxf86vm1 libxfixes3 libxrender1
BPY="$WORKDIR/blender/4.5/python/bin/python3.11"
"$BPY" -m ensurepip >/dev/null 2>&1 || true
if [ ! -d "$WORKDIR/pylibs/scipy" ]; then
  "$BPY" -m pip install --target "$WORKDIR/pylibs" scikit-image scipy
  rm -rf "$WORKDIR"/pylibs/numpy "$WORKDIR"/pylibs/numpy-* "$WORKDIR"/pylibs/numpy.libs   # keep Blender's bundled numpy
fi
export OLIVER_PYLIBS="$WORKDIR/pylibs"
export BLENDER="$WORKDIR/blender/blender"
export BPY
