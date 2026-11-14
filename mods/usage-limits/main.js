// Usage limits: every Claude Code / Codex limit window in the status bar, and one
// panel on hover: the details, and behind ⚙ the checkboxes to choose what shows.
//
// Data comes from small helpers that run the CLIs themselves (helpers/*.sh);
// this mod never reads a token. Everything below main.js is pure and tested.
import { View, div, image, svg } from "gpui-kit";
import { HoverCard, h_flex, v_flex } from "gpui-base";
import { exec, focused, theme, props, shared, setShared, appHome, layout, run } from "herdr";
import { PROVIDERS } from "./providers/index.js";
import { barModel, cardModel, chooseDensity, panelOnEnter } from "./lib/view.js";
import { effectivePrefs, isOnBar, isShown, toggleOnBar, toggleProvider, toggleShowBars, toggleShowResetTime, toggleWindow } from "./lib/prefs.js";
import { parseSession, sessionOnBar, sessionView } from "./lib/session.js";
import { nextState } from "./lib/state.js";
import { level } from "./lib/format.js";

const MOD = "usage-limits";
const KEY_STATE = "usage-limits.state";
const KEY_PREFS = "usage-limits.prefs";
const KEY_REFRESH = "usage-limits.refresh";
const FETCH_EVERY = 5 * 60;       // s, installed providers
const MISSING_EVERY = 60 * 60;    // s, not-installed providers
const REFRESH_COOLDOWN = 30;      // s
const SESSION_EVERY = 10 * 1000;   // ms, at most this often on hover
const AGENTS = { "claude-code": "claude", codex: "codex" }; // Herdr's app name → session.sh
const BAR_W = 30;
const PANEL_W = 340;
const PANEL_BAR_W = 110;
const SESSION_BAR_W = 60;
const LEFT_W = 48;                   // the time-left column in the panel
const PANEL_OPEN_DELAY = 350;       // ms, so passing over the bar doesn't flash it
const PANEL_CLOSE_DELAY = 300;      // ms, lets the pointer cross from the bar to the card
const PANEL_NODE = "panel";
const PANEL_STACK = "panel-body";
const PANEL_CHILD = "usage-limits";
const PANELS_KEY = "workspace.panels";
const BUSY_FOR = 40;
const LAST_FETCH = {};
const BUSY = {};
const VERDICTS = { "on pace": "on pace", ahead: "ahead of pace", under: "under pace" };

const now = () => Math.floor(Date.now() / 1000);
const states = () => shared(KEY_STATE) ?? {};

function levelColor(level, t) {
  if (level === "hot") return t.ansi1 ?? t.blocked;
  if (level === "warn") return t.ansi3 ?? t.done;
  return t.ansi2 ?? t.working;
}

function panelShown(node = layout()) {
  if (!node || node.hidden) return false;
  if (node.content?.mod === MOD && node.content?.props?.panel) return true;
  return (node.children ?? []).some((c) => (node.type !== "stack" || node.active === c.id) && panelShown(c));
}

function fiveHourPercent(st, at) {
  let worst = null;
  for (const p of PROVIDERS) {
    const s = st[p.id] ?? {};
    const source = s.report?.status === "ok" ? s.report : s.lastGood;
    for (const w of source?.windows ?? []) {
      if (w.durationSec !== 5 * 60 * 60 && w.short !== "5h") continue;
      if (!Number.isFinite(w.percent)) continue;
      if (w.resetsAt != null && w.resetsAt <= at) continue;
      if (worst == null || w.percent > worst) worst = w.percent;
    }
  }
  return worst;
}

const textColor = (level, text, t) => (level === "ok" ? (text === "—" ? t.dim : t.foreground) : levelColor(level, t));

// A limit's number always wears its level, green included; session numbers don't.
const limitColor = (level, text, t) => (text === "—" ? t.dim : levelColor(level, t));

function usageBar(width, fill, tick, color, t) {
  return div().relative().w(width).h(4).rounded(2).bg(t.border).flex_none()
    .child(div().absolute().left(0).top(0).h(4).rounded(2).w(Math.round(width * fill)).bg(color))
    .when(tick != null, (b) => b.child(div().absolute().top(-2).left(Math.round(width * tick)).w(1).h(8).bg(t.foreground).opacity(0.75)));
}

export default class UsageLimits extends View {
  init(_props, cx) {
    this.width = 0;
    this.panel = "limits"; // or "settings"
    this.leftAt = null;    // ms, when the pointer left the bar and the panel
    this.terminal = null;  // the focused terminal the session below belongs to
    this.session = null;   // { data: Session, title } or null
    this.sessionAt = 0;    // ms, last session read
    this.sessionBusy = false;
    this.shown = false;
    this.seenRefresh = shared(KEY_REFRESH) ?? 0;
    if (this.role() === "button") {
      const enabled = shared(PANELS_KEY) ?? ["files", "changes"];
      if (!enabled.includes(PANEL_CHILD)) setShared(PANELS_KEY, [...enabled, PANEL_CHILD]);
    }
    this.tick(cx, true);
    cx.timer.every(60 * 1000, (cx) => this.tick(cx, false));
  }

  // Fetch whatever is due, then redraw (countdowns and pace move every minute).
  tick(cx, force) {
    const st = states();
    for (const p of PROVIDERS) {
      const every = force ? REFRESH_COOLDOWN : st[p.id]?.installed === false ? MISSING_EVERY : FETCH_EVERY;
      if (now() - (LAST_FETCH[p.id] ?? 0) >= every) this.fetch(p, cx);
    }
    if (this.role() !== "button") this.readSession(cx);
    cx.notify();
  }

  fetch(p, cx) {
    if (now() - (BUSY[p.id] ?? 0) < BUSY_FOR) return;
    BUSY[p.id] = now();
    LAST_FETCH[p.id] = now();
    cx.spawn(async (cx) => {
      let next;
      const prev = states()[p.id] ?? { report: null, lastGood: null, installed: null };
      try {
        const r = await exec("sh", [`${appHome()}/mods/${MOD}/${p.helper}`]);
        next = r.code === 127 ? nextState(prev, null, false) : nextState(prev, p.parse(r.stdout, now()), true);
      } catch (e) {
        next = { ...prev, report: { status: "error", message: String(e?.message ?? e), plan: null, observedAt: now(), source: p.helper, windows: [] } };
      }
      BUSY[p.id] = 0;
      setShared(KEY_STATE, { ...states(), [p.id]: next });
      cx.notify();
    });
  }

  // Terminal → its agent's process → that process's session. Any step failing means
  // no block at all: another session's numbers would be worse than none.
  readSession(cx) {
    if (this.sessionBusy) return; // a hung hc mustn't pile up; it re-reads below if focus moved
    if (this.role() === "panel" && !panelShown()) {
      this.session = null;
      return;
    }
    const terminal = this.terminal;
    this.sessionAt = Date.now();
    if (!terminal) {
      this.session = null;
      return;
    }
    this.sessionBusy = true;
    cx.spawn(async (cx) => {
      let next = null;
      try {
        const info = JSON.parse((await exec("hc", ["get", terminal])).stdout);
        const app = AGENTS[info.status?.app];
        const pid = info.foreground?.pid;
        if (app && pid) {
          const r = await exec("sh", [`${appHome()}/mods/${MOD}/helpers/session.sh`, app, String(pid)]);
          const data = r.code === 0 ? parseSession(r.stdout, app) : null;
          if (data) next = { data, title: (info.cwd ?? "").split("/").pop() };
        }
      } catch {
        next = null;
      } finally {
        this.sessionBusy = false;
      }
      if (terminal !== this.terminal) {
        this.readSession(cx); // focus moved on while this was reading
        return;
      }
      this.session = next;
      cx.notify();
    });
  }

  role() {
    const p = props();
    return p?.button ? "button" : p?.panel ? "panel" : "bar";
  }

  cooling() {
    return now() - Math.floor((shared(KEY_REFRESH) ?? 0) / 1000) < REFRESH_COOLDOWN;
  }

  refresh(cx) {
    if (!this.cooling()) setShared(KEY_REFRESH, Date.now());
    cx.notify();
  }

  // Herdr's props come from props(), not init's first argument (shipped mods ignore it too).
  prefs() {
    return effectivePrefs(shared(KEY_PREFS), props());
  }

  hover(on, cx) {
    if (!on) {
      this.leftAt = Date.now();
      return;
    }
    this.panel = panelOnEnter(this.panel, this.leftAt, Date.now(), PANEL_CLOSE_DELAY);
    this.leftAt = null;
    if (Date.now() - this.sessionAt >= SESSION_EVERY) this.readSession(cx);
    cx.notify();
  }

  show(panel, cx) {
    this.panel = panel;
    cx.notify();
  }

  // ---------- status bar ----------

  segment(s, density, t) {
    const color = levelColor(s.level, t);
    return h_flex().gap(5).items_center().flex_none()
      .when(density < 2, (e) => e.child(div().text_size(10.5).text_color(t.dim).child(s.short)))
      .when(density === 0, (e) => e.child(usageBar(BAR_W, s.fill, s.tick, color, t)))
      .child(div().whitespace_nowrap().text_color(limitColor(s.level, s.text, t)).child(density === 3 ? s.brief : s.text));
  }

  renderBar(cx) {
    const t = theme();
    const st = states();
    const prefs = this.prefs();
    const model = barModel(st, prefs, now());
    const numbers = sessionOnBar(this.session?.data, prefs);
    const numbersWidth = numbers.reduce((w, n) => w + 7 * n.text.length + 14, numbers.length ? 14 : 0);
    const density = chooseDensity(model, this.width ? this.width - 24 - numbersWidth : Infinity, prefs.showBars);
    const root = h_flex().id("root").size_full().px(12).items_center().justify_end().overflow_hidden()
      .bg(t.chrome).border_t(1).border_color(t.border).text_size(11.8).text_color(t.muted)
      .on_size_change((size, cx) => { this.width = size.width; cx.notify(); });
    // Only the limits themselves open the panel, not the empty rest of the block.
    const content = h_flex().id("ul-content").gap(14).items_center().flex_none().on_hover((on, cx) => this.hover(on, cx));
    if (numbers.length) {
      content.child(h_flex().gap(10).items_center().flex_none()
        .children(numbers.map((n) => div().whitespace_nowrap().text_color(textColor(n.level, n.text, t)).child(n.text))));
      if (!model.empty) content.child(div().w(1).h(14).bg(t.border).flex_none());
    }
    if (model.empty) content.child(div().id("ul-empty").child(svg(`mods/${MOD}/icons/gauge.svg`).size(14)));
    model.groups.forEach((g, i) => {
      if (i > 0) content.child(div().w(1).h(14).bg(t.border).flex_none());
      content.child(
        h_flex().id(`ul-${g.providerId}`).gap(density === 0 ? 10 : 8).items_center().flex_none()
          .opacity(g.dim ? 0.55 : 1)
          .child(image(g.icon).size(13))
          .when(g.mark != null, (e) => e.child(div().text_color(t.dim).child(g.mark)))
          .children(g.segments.map((s) => this.segment(s, density, t))));
    });
    const panel = cardModel(st, now());
    // With no CLI installed there are no limits to show, so settings are all there is.
    const body = this.panel === "settings" || panel.empty ? this.settings(!panel.empty, t) : this.limits(panel, t);
    return root.child(HoverCard.new("ul-panel").anchor("bottom_right").open_delay(PANEL_OPEN_DELAY).close_delay(PANEL_CLOSE_DELAY)
      .trigger(content)
      .content(body));
  }

  // ---------- panel: limits ----------

  cardRow(r, providerId, t) {
    return v_flex().gap(3)
      .child(h_flex().id(`ul-row-${providerId}-${r.id}`).gap(8).items_center()
        .when(r.hint != null, (e) => e.tooltip(r.hint))
        .child(div().flex_1().min_w(0).truncate().text_color(t.muted).child(r.long))
        .child(usageBar(PANEL_BAR_W, r.fill, r.tick, levelColor(r.level, t), t))
        .child(div().w(64).flex_none().flex().justify_end().whitespace_nowrap().text_color(limitColor(r.level, r.percent, t)).child(r.percent))
        .child(div().w(LEFT_W).flex_none().flex().justify_end().whitespace_nowrap().text_size(11).text_color(t.dim).child(r.left)))
      .when(r.detail !== "", (e) => e.child(div().text_size(11).text_color(t.dim).truncate().child(r.detail)));
  }

  cardGroup(g, t) {
    return v_flex().gap(8)
      .child(h_flex().gap(6).items_center()
        .child(image(g.icon).size(13))
        .child(div().flex_none().font_semibold().child(g.name))
        .when(g.plan != null, (e) => e.child(div().flex_none().px(5).rounded(4).bg(t.raised).text_size(10).text_color(t.accent).child(g.plan)))
        .child(div().flex_1())
        .child(div().min_w(0).truncate().text_size(11).text_color(g.failed ? levelColor("hot", t) : t.dim).child(g.status)))
      .when(g.age != null, (e) => e.child(div().text_size(11).text_color(t.dim).child(g.age)))
      .child(v_flex().gap(6).opacity(g.dim ? 0.55 : 1).children(g.rows.map((r) => this.cardRow(r, g.providerId, t))));
  }

  sessionBlock(v, t) {
    const stats = [v.context.detail, v.calls, v.compactions, v.last].filter(Boolean).join(" · ");
    return v_flex().gap(4)
      .child(h_flex().gap(6).items_center()
        .child(div().flex_none().font_semibold().child("This session"))
        .child(div().flex_1().min_w(0).truncate().text_color(t.dim).child(v.title))
        .when(v.context.fill != null, (r) => r.child(usageBar(SESSION_BAR_W, v.context.fill, null, levelColor(v.context.level, t), t)))
        .child(div().flex_none().whitespace_nowrap().text_color(textColor(v.context.level, v.context.text, t)).child(`ctx ${v.context.text}`)))
      .child(div().text_size(11).text_color(t.dim).child(stats));
  }

  iconButton(id, icon, label, enabled, onClick, t) {
    return div().id(id).size(24).rounded(5).flex().items_center().justify_center().tooltip(label)
      .when(enabled, (e) => e.cursor_pointer().hover((s) => s.bg(t.hover)).on_click((_e, cx) => onClick(cx)))
      .child(svg(`mods/${MOD}/icons/${icon}.svg`).size(14).text_color(enabled ? t.muted : t.dim));
  }

  shell(t) {
    return v_flex().id("ul-panel-body").w(PANEL_W).p(12).gap(10).rounded(8).border(1).border_color(t.border).bg(t.popover).shadow_lg()
      .text_size(12).text_color(t.foreground)
      .on_hover((on, cx) => this.hover(on, cx));
  }

  limits(model, t) {
    const rule = () => div().h(1).bg(t.border).flex_none();
    const body = this.shell(t);
    const session = sessionView(this.session?.data, this.session?.title);
    if (session) body.child(this.sessionBlock(session, t)).child(rule());
    model.groups.forEach((g, i) => {
      if (i > 0) body.child(rule());
      body.child(this.cardGroup(g, t));
    });
    const cooling = this.cooling();
    return body.child(rule())
      .child(h_flex().gap(2).justify_end().items_center()
        .child(this.iconButton("ul-refresh", "refresh", cooling ? "Refreshing…" : "Refresh now", !cooling, (cx) => this.refresh(cx), t))
        .child(this.iconButton("ul-settings", "gear", "Settings", true, (cx) => this.show("settings", cx), t)));
  }

  // ---------- panel: settings ----------

  check(id, on, label, onToggle, t, indent = 0, extra = null) {
    return h_flex().id(id).gap(8).items_center().pl(indent).py(3).rounded(4).cursor_pointer()
      .hover((s) => s.bg(t.hover))
      .on_click((_e, cx) => { onToggle(); cx.notify(); })
      .child(div().size(13).rounded(3).border(1).border_color(on ? t.accent : t.input).bg(on ? t.accent : t.popover)
        .flex().items_center().justify_center().text_size(9).text_color(t.accent_foreground).child(on ? "✓" : ""))
      .children(label)
      .when(extra != null, (e) => e.child(div().text_color(t.dim).truncate().child(extra)));
  }

  settings(canGoBack, t) {
    const prefs = this.prefs();
    const st = states();
    const save = (p) => setShared(KEY_PREFS, p);
    const rows = [];
    for (const p of PROVIDERS) {
      const s = st[p.id] ?? {};
      const on = isShown(prefs, p.id);
      const reason = s.installed === false ? "not installed" : s.report && s.report.status !== "ok" ? s.report.message : null;
      rows.push(this.check(`p-${p.id}`, on, [image(p.icon).size(13), div().text_color(s.installed === false ? t.dim : t.foreground).child(p.name)],
        () => save(toggleProvider(this.prefs(), p.id)), t, 0, reason));
      const windows = (s.report?.status === "ok" ? s.report : s.lastGood)?.windows ?? [];
      for (const w of windows) {
        rows.push(this.check(`w-${p.id}-${w.id}`, on && isShown(prefs, p.id, w.id), [div().text_color(on ? t.muted : t.dim).child(w.long)],
          () => save(toggleWindow(this.prefs(), p.id, w.id)), t, 21));
      }
    }
    return this.shell(t)
      .child(h_flex().gap(6).items_center().h(24)
        .when(canGoBack, (e) => e.child(this.iconButton("ul-back", "back", "Back to limits", true, (cx) => this.show("limits", cx), t)))
        .child(div().font_semibold().child("Settings")))
      .child(div().text_size(11).text_color(t.dim).child("What the bar shows. This panel always shows everything."))
      .child(v_flex().gap(1).children(rows))
      .child(div().h(1).bg(t.border).flex_none())
      .child(this.check("opt-reset-time", prefs.showResetTime, [div().text_color(t.foreground).child("Always show time to reset")],
        () => save(toggleShowResetTime(this.prefs())), t))
      .child(this.check("opt-bars", prefs.showBars, [div().text_color(t.foreground).child("Show bars")],
        () => save(toggleShowBars(this.prefs())), t))
      .child(div().h(1).bg(t.border).flex_none())
      .child(v_flex().gap(1)
        .child(div().font_semibold().pb(3).child("This session"))
        .children(["Context", "Calls", "Compactions"].map((name) => {
          const row = name.toLowerCase();
          return this.check(`s-${row}`, isOnBar(prefs, row), [div().text_color(t.foreground).child(name)],
            () => save(toggleOnBar(this.prefs(), row)), t);
        })))
      .child(div().text_size(10.5).text_color(t.dim).child("Data: claude and codex CLIs, numbers from session logs."));
  }

  renderButton() {
    const t = theme();
    const on = panelShown();
    const used = fiveHourPercent(states(), now());
    const lv = used == null ? "ok" : level(used);
    return h_flex().id("root").size_full().justify_start().items_center().bg(t.chrome).border_b(1).border_color(t.border)
      .child(h_flex().id("ul-button").h(26).px(8).gap(5).flex_none().items_center().rounded(6)
        .on_size_change(size => {
          const width = Math.ceil(size.width) + 4;
          if (this.buttonWidth !== width) { this.buttonWidth = width; run("layout.resize", { id: "usage-button", px: width }); }
        })
        .text_size(12).bg(on ? t.selected : t.chrome).text_color(on ? t.foreground : t.muted)
        .hover((s) => s.bg(t.hover))
        .on_mouse_down("left", (_e, cx) => cx.stop_propagation())
        .on_click(() => {
          if (on) run("layout.hide", { id: PANEL_NODE });
          else {
            run("layout.select", { stack: PANEL_STACK, child: PANEL_CHILD });
            run("layout.show", { id: PANEL_NODE });
          }
        })
        .child(svg(`mods/${MOD}/icons/gauge.svg`).size(14).flex_none())
        .child(div().flex_none().whitespace_nowrap().child("Usage"))
        .when(used != null, (e) => e.child(div().flex_none().whitespace_nowrap().text_color(levelColor(lv, t)).tooltip("5-hour allowance remaining").child(`${Math.min(100, Math.max(0, 100 - used))}%`))));
  }

  panelRow(r, providerId, width, t) {
    const note = r.detail !== "" ? r.detail : [r.left ? `resets in ${r.left}` : null, VERDICTS[r.verdict] ?? null].filter(Boolean).join(" · ");
    return v_flex().id(`ul-prow-${providerId}-${r.id}`).gap(6)
      .when(r.hint != null, (e) => e.tooltip(r.hint))
      .child(h_flex().gap(8).items_center()
        .child(div().flex_1().min_w(0).truncate().text_color(t.muted).child(r.long))
        .child(div().flex_none().whitespace_nowrap().font_semibold().text_color(limitColor(r.level, r.percent, t)).child(r.percent)))
      .child(usageBar(width, r.fill, r.tick, levelColor(r.level, t), t))
      .when(note !== "", (e) => e.child(div().text_size(11).text_color(t.dim).child(note)));
  }

  panelGroup(g, width, t) {
    return v_flex().gap(12)
      .child(h_flex().gap(6).items_center()
        .child(image(g.icon).size(14))
        .child(div().flex_none().font_semibold().child(g.name))
        .when(g.plan != null, (e) => e.child(div().flex_none().px(5).rounded(4).bg(t.raised).text_size(10).text_color(t.accent).child(g.plan)))
        .child(div().flex_1())
        .child(div().min_w(0).truncate().text_size(11).text_color(g.failed ? levelColor("hot", t) : t.dim).child(g.status)))
      .when(g.age != null, (e) => e.child(div().text_size(11).text_color(t.dim).child(g.age)))
      .child(v_flex().gap(14).opacity(g.dim ? 0.55 : 1).children(g.rows.map((r) => this.panelRow(r, g.providerId, width, t))));
  }

  renderPanel() {
    const t = theme();
    const model = cardModel(states(), now());
    const session = sessionView(this.session?.data, this.session?.title);
    const cooling = this.cooling();
    const width = Math.max(120, (this.width || 368) - 30);
    const rule = () => div().h(1).bg(t.border).flex_none();
    const body = v_flex().id("ul-panel-scroll").flex_1().min_h(0).overflow_y_scrollbar().p(14).gap(16).text_size(12.5);
    if (session) body.child(this.sessionBlock(session, t)).child(rule());
    if (model.empty) body.child(div().text_color(t.dim).child("Neither the claude nor the codex CLI was found."));
    model.groups.forEach((g, i) => {
      if (i > 0) body.child(rule());
      body.child(this.panelGroup(g, width, t));
    });
    return v_flex().id("root").size_full().min_h(0).rounded(10).overflow_hidden().bg(t.background).border_1().border_color(t.border)
      .text_color(t.foreground).text_size(13)
      .on_size_change((size, cx) => { this.width = size.width; cx.notify(); })
      .child(h_flex().h(42).flex_none().px(14).gap(8).items_center().border_b(1).border_color(t.border)
        .child(div().font_semibold().child("Usage"))
        .child(div().flex_1())
        .child(this.iconButton("ul-refresh", "refresh", cooling ? "Refreshing…" : "Refresh now", !cooling, (cx) => this.refresh(cx), t)))
      .child(body);
  }

  render(cx) {
    const role = this.role();
    const asked = shared(KEY_REFRESH) ?? 0;
    if (asked !== this.seenRefresh) {
      this.seenRefresh = asked;
      for (const p of PROVIDERS) this.fetch(p, cx);
    }
    if (role === "button") return this.renderButton();
    const terminal = focused()?.terminal ?? null;
    const shown = role === "bar" || panelShown();
    if (terminal !== this.terminal) {
      this.terminal = terminal;
      this.session = null;
      this.readSession(cx);
    } else if (shown && !this.shown) this.readSession(cx);
    this.shown = shown;
    return role === "panel" ? this.renderPanel() : this.renderBar(cx);
  }
}
