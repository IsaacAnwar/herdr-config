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
case ":$(zsh -lic 'echo $PATH' 2>/dev/null || sh -lc 'echo $PATH'):" in
  *":$HOME/.local/bin:"*) ;;
  *) echo "Warning: $HOME/.local/bin is not on your login shell's PATH; Herdr won't find herdr-claude-math / herdr-codex-math until it is." ;;
esac
