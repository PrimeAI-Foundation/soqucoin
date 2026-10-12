#!/bin/sh
# check-linux-release.sh: a packaged Linux binary loads on any 64-bit Linux
# from Ubuntu 22.04 and Debian 12 onward, or the build fails here.
#
#   check-linux-release.sh <arch> <glibc-max> <tool-prefix> <binary>...
#
# <arch> is the word `file` prints for the architecture (x86-64 or aarch64);
# <glibc-max> the newest GLIBC_x.y symbol version the binaries may require
# (2.35 is Ubuntu 22.04's, the build host's); <tool-prefix> is "" for a
# native binary or the cross toolchain's prefix (aarch64-linux-gnu-) so that
# readelf and objdump read the right format.
#
# The v2.5.1 Linux archives shipped binaries that needed libunivalue.so.0 (the
# in-tree library, built shared and not packaged) and the build runner's Boost
# 1.74, so they loaded on no distribution as shipped. A release binary may
# need only the C library and the dynamic loader; everything else is linked in
# from depends (the static archives) and the compiler's own static runtime.
set -eu

arch=$1; glibc_max=$2; prefix=$3; shift 3
allowed=' libc.so.6 libm.so.6 libpthread.so.0 libdl.so.2 librt.so.1 ld-linux-x86-64.so.2 ld-linux-aarch64.so.1 '

for bin in "$@"; do
  file "$bin" | grep -q "$arch" || { echo "$bin is not $arch: $(file "$bin")" >&2; exit 1; }
  needed=$("${prefix}readelf" -d "$bin" | awk '/\(NEEDED\)/ { gsub(/[][]/, "", $5); print $5 }')
  for lib in $needed; do
    case "$allowed" in
      *" $lib "*) ;;
      *) echo "$bin needs $lib, which is outside the allow list ($allowed)" >&2; exit 1 ;;
    esac
  done
  top=$("${prefix}objdump" -T "$bin" | grep -oE 'GLIBC_[0-9]+\.[0-9]+' | sed 's/GLIBC_//' | sort -t. -k1,1n -k2,2n -u | tail -1)
  newest=$(printf '%s\n%s\n' "$top" "$glibc_max" | sort -t. -k1,1n -k2,2n | tail -1)
  if [ "$newest" != "$glibc_max" ]; then
    echo "$bin needs GLIBC_$top, newer than the $glibc_max floor" >&2; exit 1
  fi
  echo "$bin: $arch, NEEDED [$needed ], glibc $top (floor $glibc_max)"
done
