export const conversationKey = source => source?.engine && source?.session ? `${source.engine}:${source.session}` : null;

export function targetForFocus(focus, panes, remembered) {
  if (!focus?.tab) return null;
  const scope = JSON.stringify([focus.space, focus.tab]);
  const visible = panes.filter(p => p.tab === focus.tab && ["codex", "claude", "claude-code"].includes(p.app));
  let pane;
  if (focus.terminal) {
    pane = visible.find(p => p.terminal === focus.terminal);
    if (!pane) return null;
    remembered.set(scope, pane.terminal);
  } else {
    pane = visible.find(p => p.focused) || visible.find(p => p.terminal === remembered.get(scope));
    if (!pane && visible.length === 1) pane = visible[0];
  }
  if (!pane) return null;
  const title = (pane.title ?? "").replace(/^[^\w]+/, "");
  return { terminal: pane.terminal, space: focus.space, tab: focus.tab,
    stamp: JSON.stringify([focus.space, focus.tab, pane.terminal, pane.app, title, pane.cwd]) };
}

export class SourceSelection {
  constructor() { this.scope = null; this.key = null; this.generation = 0; this.error = ""; }
  begin(scope) {
    if (scope !== this.scope) this.key = null;
    this.scope = scope;
    this.error = "";
    return { scope, generation: ++this.generation };
  }
  matches(request) { return this.scope === request.scope && this.generation === request.generation; }
  accept(request, key) {
    if (!this.matches(request)) return false;
    this.key = key;
    this.error = "";
    return true;
  }
  fail(request, error) {
    if (!this.matches(request)) return false;
    this.key = null;
    this.error = error;
    return true;
  }
  clear(error = "") { this.scope = null; this.key = null; this.error = error; this.generation++; }
  owns(target, key = this.key) { return Boolean(target && this.scope === target.stamp && this.key === key); }
}

export function applySnapshot(chat, snapshot) {
  if (conversationKey(snapshot.source) !== chat.key) throw new Error("The side chat belongs to a different conversation.");
  const source = chat.source;
  Object.assign(chat, snapshot);
  chat.source = { ...snapshot.source, ...source };
}
