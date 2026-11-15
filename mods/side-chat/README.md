# Side chat

Click **Side chat** in Herdr's top bar to open a temporary conversation about the active Claude Code or Codex terminal.

The panel follows the active conversation. Each native conversation ID has its own side-chat history, draft, and quoted passage, including conversations within the same space. Switching back restores that conversation's side chat. Starting another conversation in the same terminal creates a separate side chat. The source is checked again before a question is sent.

Select a passage in the terminal, then press **Cmd+Option+S** to open the panel with that copied passage attached. Herdr's existing copy-on-selection mod puts the selection on the clipboard. Review or remove the quote before sending.

Type in the bottom composer and press **Enter** to send. **Shift+Enter** inserts a new line. Follow-up questions stay in the side chat. **+** discards that side chat and starts fresh from the terminal's current conversation. **×** hides the panel and keeps the side chat until Herdr closes.

The palette button in the panel header chooses an ASCII backdrop: Orbit, Dunes, Tide, Koi, Stars, Fireflies, Rain, Garden or None. Herdr's background, text and accent colors stay unchanged. The Color toggle adds a scene palette to the artwork or switches it to monochrome. Color is on by default. Scene and Color choices are saved separately for each space. Backdrops always animate while visible. The picker previews every scene; arrow keys move between tiles and Enter applies one. Changing the backdrop keeps the current chat and draft.

The original procedural artwork takes inspiration from the ASCII, braille and dither styles in [Devault's library](https://devault.design/ascii-art-generator/library/) and the backdrops in [Claude's theme examples](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/theme-examples). Transparent WebP clips play natively at 30 FPS, with gentle eight- to sixteen-second loops. Koi has orange and gold fish with bending bodies, moving fins, lily pads and a small water lily. Dunes has a gently moving striped sun and textured sand. Orbit, Dunes, Tide, Rain and Garden concentrate their detail along the bottom and bottom-right, leaving the upper area open. Stars has brighter twinkling stars and occasional shooting stars. Orbit adds a crescent moon and a more widely spaced star field. Fireflies replaces Ripples with drifting lights above meadow grass. Existing Ripples choices switch to Fireflies. Artwork scales to cover the panel. Both color and monochrome modes adapt their ink to the current Herdr background. No images or scripts are loaded from those sites.

The panel identifies the source session from Herdr's foreground process and the installed CLI's session metadata. It refuses ambiguous Codex task names rather than choosing the newest chat in the same folder. Use `/rename` in Codex if it asks for a unique name.

Codex uses an in-memory `thread/fork` through its app server. Claude uses `--resume --fork-session --no-session-persistence` with a streaming process that holds follow-ups in memory. Both use the installed CLI's authentication. Side chats use the source provider's limits.

Conversation text stays in the panel and helper process memory. A private Unix socket carries messages locally. The panel does not write chat history to Herdr shared state or the main session. Helpers exit and remove their sockets when closed, or after three minutes without a heartbeat. Main terminal sessions keep running.

Side chats answer from inherited context. Claude's tools and hooks are disabled. Codex runs with a read-only sandbox, shell execution, plugins, hooks, and multi-agent features disabled, plus instructions to answer without taking actions.

This version supports local Claude Code and Codex terminals. It does not yet attach to agents running on remote machines.

Validation:

```sh
herdr-app check ~/.config/herdr-app/mods/side-chat
python3 ~/.config/herdr-app/mods/side-chat/test_backend.py
node --test ~/.config/herdr-app/mods/side-chat/scope.test.mjs
```

The generated assets are included, so playback needs no extra tools. To rebuild them, install `scripts/requirements.txt` into `~/.local/share/herdr-art-tools`, then run `python3 ~/.config/herdr-app/mods/side-chat/scripts/generate-backdrops.py`.
