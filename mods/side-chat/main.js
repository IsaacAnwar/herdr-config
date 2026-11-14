import { View, div, svg } from "gpui-kit";
import { h_flex, v_flex, Textarea, TextareaState, TextView, ScrollHandle } from "gpui-base";
import { appHome, exec, focused, panes, layout, nextCommand, props, run, setShared, shared, theme } from "herdr";
import { conversationKey, targetForFocus, SourceSelection, applySnapshot } from "./scope.js";

// Shared only by live copies of this mod. Conversation text is never persisted.
const chats = new Map();
const selection = new SourceSelection();
const rememberedTerminals = new Map();
const sourceRequests = new Map();
const pendingQuotes = new Map();
let lastSourceCheck = 0;
let sequence = 0;
let focusRevision = 0;
let sendRevision = 0;
let newlineRevision = 0;
const icon = (name, size = 14) => svg(`mods/side-chat/${name}.svg`).size(size).flex_none();
const signal = () => setShared("side-chat.signal", ++sequence);
const helper = () => `${appHome()}/mods/side-chat/backend.py`;
const target = () => targetForFocus(focused(), panes(), rememberedTerminals);
const currentChat = () => selection.owns(target()) ? chats.get(selection.key) : null;

async function backend(op, ...args) {
  const result = await exec("python3", [helper(), op, ...args], { timeout: 15000 });
  let data;
  try { data = JSON.parse(result.stdout); } catch (_) { throw new Error("Could not connect to the side chat service."); }
  if (result.code || (data.error && !data.token)) throw new Error(data.error || "The side chat service is unavailable.");
  return data;
}

function find(node, id) {
  if (node?.id === id) return node;
  for (const child of node?.children ?? []) { const found = find(child, id); if (found) return found; }
  return null;
}

function shown() {
  return !find(layout(), "panel")?.hidden && find(layout(), "panel-body")?.active === "side-chat";
}

function reveal() {
  const panel = find(layout(), "panel");
  if ((panel?.size?.px ?? 368) < 360) run("layout.resize", { id: "panel", px: 400 });
  run("layout.select", { stack: "panel-body", child: "side-chat" });
  run("layout.show", { id: "panel" });
}

export default class SideChat extends View {
  init(_props, cx) {
    if (props()?.controller) {
      const panels = shared("workspace.panels") ?? [];
      setShared("workspace.panels", [...new Set(panels.filter(id => id !== "files").concat("side-chat"))]);
      this.polling = false;
      this.lastHeartbeat = 0;
      cx.spawn(async cx => {
        for (;;) {
          const command = await nextCommand();
          if (command === "open" || command === "quote") this.open(command === "quote", cx);
          if (command === "unquote") { const chat = currentChat(); if (chat) { chat.quote = ""; signal(); } }
          if (command === "new") this.reset(cx);
          if (command === "send") { sendRevision++; signal(); }
          if (command === "newline") { newlineRevision++; signal(); }
          if (command === "focus" && shown()) signal();
        }
      });
      cx.timer.every(500, cx => this.poll(cx));
      return;
    }
    this.bound = null;
    this.scroll = ScrollHandle.new();
    this.messageCount = 0;
    this.visible = false;
    cx.timer.after(16, cx => { this.visible = true; cx.notify(); });
    this.input = TextareaState.new({ placeholder: "Ask a question...", rows: 2 });
    this.input.set_soft_wrap(true);
    this.input.on("focus", (_event, cx) => { this.composerFocused = true; cx.notify(); });
    this.input.on("blur", (_event, cx) => { this.composerFocused = false; cx.notify(); });
    this.input.on("change", (_event, cx) => {
      if (this.bound) this.bound.draft = this.input.value();
      cx.notify();
    });
    this.input.on("submit", (_event, cx) => this.send(cx));
    cx.timer.after(50, cx => { if (shown() && !currentChat()) this.open(false, cx); });
    this.seenFocus = 0;
    this.seenSend = 0;
    this.seenNewline = 0;
    cx.timer.every(200, cx => {
      if (!shown()) return;
      if (this.seenFocus !== focusRevision) {
        this.seenFocus = focusRevision;
        this.input.focus();
      }
      if (this.seenSend !== sendRevision) {
        this.seenSend = sendRevision;
        this.send(cx);
      }
      if (this.seenNewline !== newlineRevision) {
        const count = newlineRevision - this.seenNewline;
        this.seenNewline = newlineRevision;
        this.input.replace("\n".repeat(Math.max(0, count)));
      }
    });
    cx.spawn(async cx => {
      for (;;) {
        const command = await nextCommand();
        if (command === "focus") this.input.focus();
        if (command === "send") this.send(cx);
      }
    });
  }

  open(withQuote, cx) {
    const active = target();
    if (withQuote && active) {
      const text = cx.read_from_clipboard()?.trim();
      if (text) pendingQuotes.set(active.stamp, text.slice(0, 20000));
    }
    reveal();
    focusRevision++;
    this.syncSource(cx, true);
    signal();
  }

  syncSource(cx, force = false) {
    if (!shown()) return;
    const active = target();
    if (!active) {
      if (selection.scope || !selection.error) {
        selection.clear("Select a Claude Code or Codex conversation.");
        signal();
      }
      return;
    }
    const changed = active.stamp !== selection.scope;
    if (sourceRequests.has(active.stamp)) return;
    if (!force && !changed && Date.now() - lastSourceCheck < 2000) return;
    const request = selection.begin(active.stamp);
    sourceRequests.set(active.stamp, request);
    lastSourceCheck = Date.now();
    if (changed) signal();
    cx.spawn(async cx => {
      try {
        const source = await backend("source", active.terminal);
        if (target()?.stamp !== active.stamp || !selection.matches(request)) return;
        const key = conversationKey(source);
        if (!key) throw new Error("This conversation has no session ID yet.");
        let chat = chats.get(key);
        if (!chat) {
          chat = { key, terminal: active.terminal, source, token: null, connecting: true,
            messages: [], draft: "", quote: "", error: "" };
          chats.set(key, chat);
          this.connect(chat, cx);
        } else {
          chat.terminal = active.terminal;
          chat.source = source;
        }
        if (!selection.accept(request, key)) return;
        if (pendingQuotes.has(active.stamp)) {
          chat.quote = pendingQuotes.get(active.stamp);
          pendingQuotes.delete(active.stamp);
        }
        signal(); cx.notify();
      } catch (error) {
        if (target()?.stamp === active.stamp && selection.fail(request, error.message)) { signal(); cx.notify(); }
      } finally {
        if (sourceRequests.get(active.stamp) === request) sourceRequests.delete(active.stamp);
      }
    });
  }

  connect(chat, cx) {
    cx.spawn(async cx => {
      try {
        const result = await backend(chat.fresh ? "new" : "attach", chat.terminal, chat.key);
        if (chats.get(chat.key) !== chat) return;
        applySnapshot(chat, result);
        chat.connecting = false;
      } catch (error) { chat.error = error.message; chat.connecting = false; }
      signal(); cx.notify();
    });
  }

  poll(cx) {
    this.syncSource(cx);
    if (this.polling) return;
    const heartbeat = Date.now() - this.lastHeartbeat > 15000;
    const active = [...chats.values()].filter(chat => chat.token && (chat.busy || heartbeat));
    if (!active.length) return;
    this.polling = true;
    if (heartbeat) this.lastHeartbeat = Date.now();
    cx.spawn(async cx => {
      let changed = false;
      try {
        for (const chat of active) {
          if (chats.get(chat.key) !== chat) continue;
          try {
            const next = await backend("status", chat.token);
            if (next.revision !== chat.revision || next.busy !== chat.busy) { applySnapshot(chat, next); changed = true; }
          } catch (error) {
            chat.error = error.message; chat.busy = false; chat.phase = "ended"; chat.token = null; changed = true;
          }
        }
      } finally {
        this.polling = false;
        if (changed) { signal(); cx.notify(); }
      }
    });
  }

  send(cx) {
    const chat = currentChat(), active = target();
    const question = this.input.value().trim();
    if (!chat?.token || chat !== this.bound || chat.busy || chat.sending || !question || chat.phase === "ended") return;
    const oldDraft = this.input.value(), quote = chat.quote;
    const text = quote ? `Selected passage:\n${quote.split("\n").map(line => `> ${line}`).join("\n")}\n\n${question}` : question;
    chat.sending = true;
    let cleared = false;
    cx.spawn(async cx => {
      try {
        const source = await backend("source", active.terminal);
        if (target()?.stamp !== active.stamp || !selection.owns(active, chat.key)) return;
        if (conversationKey(source) !== chat.key) { this.syncSource(cx, true); return; }
        if (this.bound !== chat || this.input.value() !== oldDraft || chat.quote !== quote) return;
        chat.busy = true; chat.error = ""; chat.draft = ""; chat.quote = "";
        this.input.set_value(""); cleared = true; signal();
        applySnapshot(chat, await backend("ask", chat.token, text));
      } catch (error) {
        chat.error = error.message; chat.busy = false;
        if (cleared) {
          chat.draft = oldDraft; chat.quote = quote;
          if (currentChat() === chat && this.bound === chat) this.input.set_value(oldDraft);
        }
      } finally { chat.sending = false; signal(); cx.notify(); }
    });
  }

  reset(cx) {
    const chat = currentChat();
    if (!chat?.terminal) return;
    if (chat.token) cx.spawn(async () => { try { await backend("close", chat.token); } catch (_) {} });
    const next = { key: chat.key, source: chat.source, terminal: chat.terminal, token: null,
      connecting: true, fresh: true, messages: [], draft: "", quote: "", error: "" };
    chats.set(chat.key, next);
    this.bound = null;
    this.connect(next, cx); signal(); cx.notify();
  }

  control(id, glyph, hint, action, t) {
    return div().id(id).size(25).rounded(6).flex_none().flex().items_center().justify_center()
      .text_color(t.muted).cursor_pointer().hover(s => s.bg(t.hover).text_color(t.foreground))
      .tooltip(hint).on_mouse_down("left", (_e, cx) => cx.stop_propagation()).on_click(action).child(glyph);
  }

  async close() {
    if (!props()?.controller) return;
    const tokens = [...chats.values()].map(chat => chat.token).filter(Boolean);
    chats.clear(); selection.clear(); rememberedTerminals.clear(); pendingQuotes.clear();
    await Promise.all(tokens.map(async token => { try { await backend("close", token); } catch (_) {} }));
  }

  render(cx) {
    if (props()?.controller) return div();
    const t = theme(), chat = currentChat();
    if (this.bound !== chat) {
      this.bound = chat;
      this.input.set_value(chat?.draft ?? "");
      this.messageCount = 0;
    }
    if ((chat?.messages?.length ?? 0) !== this.messageCount) {
      this.messageCount = chat?.messages?.length ?? 0;
      if (this.messageCount) this.scroll.scroll_to_item(this.messageCount - 1);
    }
    const active = target();
    const scoped = active ? selection.scope === active.stamp : selection.scope === null;
    const error = chat?.error || (scoped ? selection.error : "");
    const busy = Boolean(chat?.busy || chat?.connecting || (!chat && shown() && active && !error));
    const source = chat?.source ? `${chat.source.agent} · ${chat.source.title}` : "Side chat";
    const root = v_flex().id("side-chat").size_full().min_h(0).rounded(10).overflow_hidden()
      .bg(t.background).border_1().border_color(t.border).text_color(t.foreground).text_size(13)
      .opacity(this.visible ? 1 : 0).transition("opacity", { duration: 140, easing: "ease-out" })
      .on_key_down((event, cx) => {
        if (event.key === "enter" && !event.modifiers.shift) { cx.stop_propagation(); this.send(cx); }
      })
      .child(h_flex().h(42).flex_none().px(14).gap(7).items_center()
        .child(div().font_medium().text_size(12).text_color(t.muted).tooltip(source).child("Side chat"))
        .child(div().flex_1())
        .when(Boolean(chat?.busy), el => el.child(this.control("side-stop", div().size(8).rounded(2).bg(t.muted), "Stop response", (_e, cx) => {
          cx.spawn(async cx => { try { applySnapshot(chat, await backend("cancel", chat.token)); } catch (error) { chat.error = error.message; } signal(); cx.notify(); });
        }, t)))
        .child(this.control("side-new", div().text_size(18).child("+"), "New side chat", (_e, cx) => this.reset(cx), t))
        .child(this.control("side-hide", div().text_size(17).child("×"), "Hide side chat", () => run("layout.hide", { id: "panel" }), t)));

    const body = v_flex().id(`side-messages-${chat?.token ?? "empty"}`).flex_1().min_h(0)
      .overflow_y_scrollbar().track_scroll(this.scroll).px(16).py(12).gap(20);
    for (const [index, message] of (chat?.messages ?? []).entries()) {
      if (!message.text && busy) continue;
      const text = TextView.markdown(`side-message-${chat.token}-${index}`, message.text || "Response stopped.")
        .selectable(true).text_size(13).text_color(t.foreground);
      body.child(message.role === "user"
        ? div().px(11).py(9).rounded(8).bg(t.raised).child(text)
        : div().child(text));
    }
    if (busy) body.child(svg("mods/workspace-chrome/spinner.svg").size(13).flex_none().text_color(t.dim).spin(900));
    if (error) body.child(v_flex().py(8).gap(8)
      .child(div().text_size(12).text_color(t.blocked).child(error))
      .child(div().id("side-retry").text_size(11).text_color(t.accent).cursor_pointer()
        .on_click((_e, cx) => { if (chat?.terminal) this.reset(cx); else this.syncSource(cx, true); }).child("Try again")));
    root.child(body);

    const composer = v_flex().flex_none().px(12).pb(12).pt(4).gap(8);
    if (chat?.quote) composer.child(h_flex().px(10).py(7).gap(8).rounded(6).bg(t.chrome)
      .border_l(2).border_color(t.accent).items_center()
      .child(div().flex_1().min_w(0).text_size(11).truncate().text_color(t.muted)
        .tooltip(chat.quote).child(chat.quote.replace(/\s+/g, " ")))
      .child(this.control("side-unquote", div().child("×"), "Remove quote", (_e, cx) => { chat.quote = ""; signal(); cx.notify(); }, t)));
    const lines = this.input.value().split("\n").length;
    composer.child(div().h(Math.min(136, Math.max(62, 30 + lines * 18))).relative().rounded(10)
      .bg(t.chrome).border_1().border_color(this.composerFocused ? t.input : t.border)
      .tooltip("Enter to send · Shift+Enter for a new line")
      .child(Textarea.new(this.input).absolute().inset_0().size_full().px(12).py(11).text_size(13).text_color(t.foreground)));
    return root.child(composer);
  }
}
