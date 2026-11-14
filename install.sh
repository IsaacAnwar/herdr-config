#!/bin/sh
set -e
here="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HOME/.config/herdr" "$HOME/.local/bin" "$HOME/.local/share/herdr-tformula"
cp "$here/extras/herdr/config.toml" "$HOME/.config/herdr/config.toml"
cp "$here/extras/bin/"herdr-* "$HOME/.local/bin/"
chmod +x "$HOME/.local/bin/"herdr-claude-math "$HOME/.local/bin/"herdr-codex-math
cp "$here/extras/tformula/package.json" "$here/extras/tformula/package-lock.json" "$HOME/.local/share/herdr-tformula/"
(cd "$HOME/.local/share/herdr-tformula" && npm ci)
ln -sf "$HOME/.local/share/herdr-tformula/node_modules/tformula/dist/cli.js" "$HOME/.local/bin/tformula"
echo "Installed config.toml, tformula and herdr-*-math. Restart Herdr, then run: herdr-app check"
