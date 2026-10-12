#!/bin/sh
# smoke-linux-release.sh: unpack a packaged Linux archive into clean
# distribution containers and run the two programs there.
#
#   smoke-linux-release.sh <archive.tar.gz> <docker-platform> <image>...
#
# In each image: both programs print their version, the daemon starts a
# regtest node in a temporary data directory, answers getblockchaininfo and
# getblockhash 0, and stops cleanly. The images carry nothing beyond their
# base packages, which is the point: a release archive has to run there.
# Under qemu (the arm64 platform on an x86-64 runner) the start is slow, so
# the poll allows two minutes.
set -eu

archive=$1; platform=$2; shift 2
work=$(mktemp -d)
mkdir -p "$work/bin"
tar -xzf "$archive" -C "$work/bin"
test -x "$work/bin/soqucoind" && test -x "$work/bin/soqucoin-cli"

for image in "$@"; do
  echo "== $image ($platform)"
  docker run --rm --platform "$platform" -v "$work/bin:/a:ro" "$image" /bin/sh -c '
    set -eu
    /a/soqucoind --version | head -1
    /a/soqucoin-cli --version | head -1
    mkdir -p /d
    /a/soqucoind -regtest -datadir=/d -daemon=0 -printtoconsole=0 -disablewallet=1 -listen=0 &
    pid=$!
    i=0
    until /a/soqucoin-cli -regtest -datadir=/d getblockchaininfo > /tmp/info 2>/dev/null; do
      i=$((i + 1))
      if [ "$i" -gt 120 ]; then echo "the regtest node did not answer within 120 s" >&2; kill "$pid" 2>/dev/null || true; exit 1; fi
      if ! kill -0 "$pid" 2>/dev/null; then echo "the daemon exited before answering" >&2; exit 1; fi
      sleep 1
    done
    grep -o "\"chain\": *\"regtest\"" /tmp/info
    /a/soqucoin-cli -regtest -datadir=/d getblockhash 0
    /a/soqucoin-cli -regtest -datadir=/d stop > /dev/null
    wait "$pid"
    echo "regtest start and stop ok after ${i}s"
  '
done
rm -rf "$work"
