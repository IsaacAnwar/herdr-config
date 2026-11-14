# Side chat

Click **Side chat** in Herdr's top bar to open a temporary conversation about the active Claude Code or Codex terminal.

The panel follows the active conversation. Each native conversation ID has its own side-chat history, draft, and quoted passage, including conversations within the same space. Switching back restores that conversation's side chat. Starting another conversation in the same terminal creates a separate side chat. The source is checked again before a question is sent.

Select a passage in the terminal, then press **Cmd+Option+S** to open the panel with that copied passage attached. Herdr's existing copy-on-selection mod puts the selection on the clipboard. Review or remove the quote before sending.

Type in the bottom composer and press **Enter** to send. **Shift+Enter** inserts a new line. Follow-up questions stay in the side chat. **+** discards that side chat and starts fresh from the terminal's current conversation. **×** hides the panel and keeps the side chat until Herdr closes.

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
