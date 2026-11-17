# herdr-config

My Herdr app setup: mods, layouts, themes, keys, settings and program icons.

## New machine

    git clone https://github.com/isaaacAnwar/herdr-config.git ~/.config/herdr-app
    ~/.config/herdr-app/install.sh

If `~/.config/herdr-app` already exists (Herdr was launched once), quit Herdr and run:

    cd ~/.config/herdr-app
    git init -b main
    git remote add origin https://github.com/isaaacAnwar/herdr-config.git
    git fetch origin
    git reset --hard origin/main
    ./install.sh

`install.sh` needs Node/npm (for `tformula`, used by the `herdr-*-math` agent wrappers). `programs.json` starts the `herdr-*-math` wrappers by name, so `~/.local/bin` must be on your login shell's `PATH` (`install.sh` warns if it is not).

## Updating

    cd ~/.config/herdr-app && git add -A && git commit -m "update" && git push
    cd ~/.config/herdr-app && git pull
