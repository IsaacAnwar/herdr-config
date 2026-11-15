import { View, div, image, svg } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { props, closeOverlay, run, theme, terminals } from "herdr";

const glyph = (name, size) => svg(`mods/my-toast/${name}.svg`).size(size).flex_none();

export default class Toast extends View {
  init(_props, cx) {
    this.visible = false;
    this.copied = false;
    cx.timer.after(20, cx => { this.visible = true; cx.notify(); });
  }

  render() {
    const t = theme(), p = props() ?? {};
    const agent = p.action?.name === "agent.focus";
    const program = agent ? terminals().find(a => a.address === p.action.args?.terminal)?.program : null;
    const agentIcon = program?.icon || (agent ? p.icon : null);
    const finished = agent && /finished$/i.test(p.title ?? "");
    const waiting = agent && /needs you$/i.test(p.title ?? "");
    const error = p.level === "error";
    const warning = waiting || p.level === "warning";
    const success = finished || p.level === "success";
    const color = error ? t.blocked : warning ? t.working : success ? t.done : t.muted;
    const name = (p.title ?? "Agent").replace(/\s+(finished|needs you)$/i, "");
    const context = String(p.body ?? "").split(/\s+\/\s+/).filter(Boolean);
    const task = context.length > 1 ? context.slice(1).join(" / ") : "";
    const space = context[0] ?? "";
    const title = agent && task ? task : p.title || "Herdr";
    const detail = agent && task
      ? `${name} ${finished ? "finished" : waiting ? "needs you" : "updated"}${space ? ` · ${space}` : ""}`
      : p.body ?? "";
    const login = /^([a-z0-9][a-z0-9_.-]{0,31}) needs login; run hc machine login \1$/.exec(p.body ?? "");
    const command = login ? `hc machine login ${login[1]}` : null;
    const open = () => {
      if (p.action?.name) run(p.action.name, p.action.args ?? {});
      closeOverlay(p.overlay);
    };

    const mark = div().size(30).rounded(8).flex_none().flex().items_center().justify_center()
      .bg(t.raised).text_color(color)
      .child(agentIcon
        ? program?.tint ? svg(agentIcon).size(20).text_color(t.foreground) : image(agentIcon).size(20)
        : !p.icon ? glyph(success ? "check" : error || warning ? "alert" : "bell", 16) : image(p.icon).size(16));

    return h_flex().id("toast").size_full().px(16).gap(12).items_center()
      .rounded(10).bg(t.popover).text_color(t.foreground)
      .opacity(this.visible ? 1 : 0).transition("opacity", { duration: 150, easing: "ease-out" })
      .cursor_pointer().on_click(open)
      .accessibility_label([title, detail].filter(Boolean).join(". "))
      .tooltip([p.title, p.body, p.action?.name ? "Click to open" : null].filter(Boolean).join("\n"))
      .child(mark)
      .child(v_flex().flex_1().min_w(0).gap(4)
        .child(div().truncate().font_medium().text_size(13).child(title))
        .when(Boolean(detail || command), el => el.child(
          div().truncate().text_size(11.5).text_color(t.muted).child(command ?? detail))))
      .when(Boolean(command), el => el.child(div().id("toast-login-copy").flex_none().px(7).py(4)
        .rounded(4).bg(t.raised).text_size(11).text_color(t.muted).cursor_pointer()
        .on_mouse_down("left", (_e, cx) => cx.stop_propagation())
        .on_click((_e, cx) => { cx.stop_propagation(); cx.write_to_clipboard(command); this.copied = true; cx.notify(); })
        .child(this.copied ? "Copied" : "Copy")))
      .child(div().id("toast-dismiss").size(22).flex_none().rounded(5).flex().items_center().justify_center()
        .text_color(t.dim).hover(s => s.bg(t.hover).text_color(t.foreground))
        .tooltip("Dismiss").accessibility_label("Dismiss notification")
        .on_mouse_down("left", (_e, cx) => cx.stop_propagation())
        .on_click((_e, cx) => { cx.stop_propagation(); closeOverlay(p.overlay); })
        .child(glyph("close", 12)));
  }
}
