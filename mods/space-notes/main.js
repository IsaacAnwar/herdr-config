import { View, div, svg } from "gpui-kit";
import { v_flex, h_flex, TextareaState, Textarea } from "gpui-base";
import { spaces, theme, shared, setShared, props, layout, run } from "herdr";

const NOTES = "space-notes.entries";
const icon = (name, size = 14) => svg(`mods/space-notes/${name}.svg`).size(size).flex_none();

function find(node, id) {
  if (node?.id === id) return node;
  for (const child of node?.children ?? []) { const match = find(child, id); if (match) return match; }
  return null;
}

function panelShown() {
  const root = layout();
  return !find(root, "panel")?.hidden && find(root, "panel-body")?.active === "notes";
}

export default class SpaceNotes extends View {
  init(_props, cx) {
    if (props()?.button) {
      const enabled = shared("workspace.panels") ?? ["files", "git"];
      if (!enabled.includes("notes")) setShared("workspace.panels", [...enabled, "notes"]);
      return;
    }
    this.text = ""; this.space = null; this.dirty = false;
    this.input = TextareaState.new({ placeholder: "", rows: 24 });
    this.input.set_soft_wrap(true);
    this.input.on("change", (_e, cx) => {
      const text = this.input.value();
      if (!this.space || text === this.text) return;
      this.text = text; this.dirty = true; this.changedAt = Date.now(); cx.notify();
    });
    this.input.on("blur", (_e, cx) => { this.save(); cx.notify(); });
    cx.timer.every(500, cx => {
      if (this.dirty && Date.now() - this.changedAt >= 400) { this.save(); cx.notify(); }
    });
    this.sync();
  }

  save() {
    if (!this.space || !this.dirty) return;
    const id = this.space, text = this.text, updatedAt = Date.now();
    this.dirty = false; this.updatedAt = updatedAt;
    setShared(NOTES, { ...(shared(NOTES) ?? {}), [id]: { text, updatedAt } });
  }

  sync() {
    const current = spaces().find(s => s.active);
    const id = current?.id ?? null;
    if (id !== this.space) {
      this.save();
      const note = shared(NOTES)?.[id];
      this.space = id; this.text = note?.text ?? ""; this.updatedAt = note?.updatedAt ?? null;
      this.input.set_value(this.text);
    } else if (!this.dirty) {
      const note = shared(NOTES)?.[id];
      if ((note?.text ?? "") !== this.text) {
        this.text = note?.text ?? ""; this.updatedAt = note?.updatedAt ?? null;
        this.input.set_value(this.text);
      }
    }
    this.name = current?.name ?? "No space selected";
  }

  close() { if (!props()?.button) this.save(); }

  control(id, label, onClick, t) {
    return div().id(id).h(26).px(8).rounded(5).flex().items_center().justify_center().text_size(11.5)
      .text_color(t.muted)
      .cursor_pointer().hover(s => s.bg(t.hover)).on_click(onClick).child(label);
  }

  renderButton(t) {
    const on = panelShown();
    const space = spaces().find(s => s.active);
    const hasNotes = Boolean(shared(NOTES)?.[space?.id]?.text?.trim());
    return h_flex().size_full().items_center().justify_start().bg(t.chrome).border_b(1).border_color(t.border)
      .child(h_flex().id("space-notes-button").h(26).px(8).gap(5).flex_none().rounded(6).items_center().text_size(12)
        .on_size_change(size => {
          const width = Math.ceil(size.width) + 10;
          if (this.buttonWidth !== width) { this.buttonWidth = width; run("layout.resize", { id: "notes-button", px: width }); }
        })
        .bg(on ? t.selected : t.chrome).text_color(on ? t.foreground : t.muted).cursor_pointer().hover(s => s.bg(t.hover))
        .on_mouse_down("left", (_e, cx) => cx.stop_propagation())
        .on_click(() => {
          if (on) run("layout.hide", { id: "panel" });
          else { run("layout.select", { stack: "panel-body", child: "notes" }); run("layout.show", { id: "panel" }); }
        })
        .child(icon("note")).child("Notes")
        .when(hasNotes, e => e.child(div().size(4).rounded(2).bg(t.accent))));
  }

  render(cx) {
    const t = theme();
    if (props()?.button) return this.renderButton(t);
    this.sync();
    const root = v_flex().id("space-notes").size_full().min_h(0).rounded(10).overflow_hidden()
      .bg(t.background).border_1().border_color(t.border).text_color(t.foreground).text_size(13)
      .child(h_flex().h(42).flex_none().px(12).gap(7).items_center().border_b(1).border_color(t.border)
        .child(div().font_semibold().child("Notes"))
        .child(div().flex_1().min_w(0).truncate().text_size(11).text_color(t.dim).child(this.name))
        .child(div().text_size(10).text_color(t.dim).child(this.dirty ? "Saving…" : this.updatedAt ? "Saved" : ""))
        .child(this.control("notes-hide", "×", () => { this.save(); run("layout.hide", { id: "panel" }); }, t)));
    if (!this.space) return root;
    return root.child(div().flex_1().min_h(0).relative()
      .child(Textarea.new(this.input).absolute().inset_0().size_full().p(16).text_size(13).text_color(t.foreground)));
  }
}
