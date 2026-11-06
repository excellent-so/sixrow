#!/bin/sh
# Screenshot a local HTML file with headless Chrome:  tools/shot.sh <file.html> <out.png> [width] [height]
f="$1"; out="$2"; w="${3:-1280}"; h="${4:-4000}"
case "$f" in /*) ;; *) f="$(pwd)/$f";; esac
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --hide-scrollbars \
  --window-size="$w,$h" --virtual-time-budget=7000 --screenshot="$out" "file://$f" >/dev/null 2>&1
echo "$out"
