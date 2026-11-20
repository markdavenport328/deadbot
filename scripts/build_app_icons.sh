#!/bin/sh
# Render Deadbot's app icon and lock-screen artwork from web/icon-source/app-icon.svg
# into web/public/icons, using macOS's built-in renderers (qlmanage, sips).
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
source_dir="$root/web/icon-source"
out="$root/web/public/icons"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$out"
(cd "$source_dir" && qlmanage -t -s 1024 -o "$work" app-icon.svg >/dev/null)
master="$work/app-icon.svg.png"
cp "$master" "$out/icon-1024.png"
for size in 512 192 180; do
  sips -s format png -z "$size" "$size" "$master" --out "$work/$size.png" >/dev/null
done
cp "$work/512.png" "$out/icon-512.png"
cp "$work/192.png" "$out/icon-192.png"
cp "$work/180.png" "$out/apple-touch-icon.png"
echo "Wrote $(ls "$out" | tr '\n' ' ')"
