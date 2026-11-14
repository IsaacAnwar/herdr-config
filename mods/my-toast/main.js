import { View, div, image, svg } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { props, closeOverlay, run, theme, terminals } from "herdr";

const glyph = (name, size = 14) => svg(`mods/my-toast/${name}.svg`).size(size).flex_none();
const wash = (color, opacity) => `${color.slice(0, 7)}${Math.round(opacity * 255).toString(16).padStart(2, "0")}`;

export default class Toast extends View {
  init(_props, cx) {
    this.entered = false;
    cx.timer.after(40, cx => { this.entered = true; cx.notify(); });
  }

  render() {
    const t = theme(), p = props() ?? {};
    const isAgent = p.action?.name === "agent.focus";
    const finished = isAgent && /finished$/i.test(p.title ?? "");
    const needsYou = isAgent && /needs you$/i.test(p.title ?? "");
    const success = finished || p.level === "success";
    const warning = needsYou || p.level === "warning";
    const error = p.level === "error";
    const color = success ? t.ansi2 : warning ? t.ansi3 : error ? t.ansi1 : t.accent;
    const status = success ? "Task complete" : warning ? "Needs your attention" : error ? "Something went wrong" : "Notification";
    const title = isAgent ? (p.title ?? "Agent").replace(/\s+(finished|needs you)$/i, "") : p.title ?? "Herdr";
    const terminal = isAgent ? terminals().find(a => a.address === p.action.args?.terminal) : null;
    const program = terminal?.program;
    const login = /^([a-z0-9][a-z0-9_.-]{0,31}) needs login; run hc machine login \1$/.exec(p.body ?? "");
    const command = login ? `hc machine login ${login[1]}` : null;
    const open = () => {
      if (p.action?.name) run(p.action.name, p.action.args ?? {});
      closeOverlay(p.overlay);
    };

    const emblem = div().relative().size(40).rounded(20).flex_none().flex().items_center().justify_center()
      .bg(wash(color, 0.08)).border_1().border_color(wash(color, 0.22))
      .child(div().size(28).rounded(14).flex().items_center().justify_center().bg(wash(color, 0.13))
        .child(glyph(success ? "check" : warning || error ? "alert" : "bell", 17).text_color(color)))
      .when(Boolean(program?.icon || p.icon), el => el.child(
        div().absolute().right(-3).bottom(-2).size(17).rounded(6).border(2).border_color(t.popover)
          .bg(t.raised).flex().items_center().justify_center()
          .child(program?.icon
            ? program.tint ? svg(program.icon).size(11).text_color(t.foreground) : image(program.icon).size(11)
            : image(p.icon).size(11))));

    return h_flex().id("toast").relative().size_full().rounded(8).overflow_hidden()
      .bg(t.popover)
      .opacity(this.entered ? 1 : 0).transition("opacity", { duration: 180, easing: "ease-out" })
      .when(Boolean(p.action?.name), el => el.cursor_pointer().on_click(open))
      .hover(s => s.bg(t.raised))
      .tooltip([p.title, p.body, p.action?.name ? "Click to open" : null].filter(Boolean).join("\n"))
      .child(div().absolute().inset_0().bg(wash(color, 0.025)))
      .child(div().absolute().top(0).left(24).w(62).h(1).bg(wash(color, 0.5)))
      .child(h_flex().relative().size_full().px(14).gap(12).items_center()
        .child(emblem)
        .child(v_flex().flex_1().min_w(0).gap(2)
          .child(h_flex().gap(5).items_center()
            .child(div().size(4).rounded(2).flex_none().bg(color))
            .child(div().text_size(10).font_semibold().text_color(color).child(status)))
          .child(div().truncate().font_semibold().text_size(13).text_color(t.foreground).child(title))
          .when(Boolean(p.body), el => el.child(div().truncate().text_size(11).text_color(t.muted).child(command ?? p.body))))
        .child(v_flex().gap(5).flex_none().items_center()
          .child(div().id("toast-dismiss").size(20).rounded(6).flex().items_center().justify_center().text_color(t.dim)
            .hover(s => s.bg(t.hover).text_color(t.foreground)).tooltip("Dismiss")
            .on_mouse_down("left", (_e, cx) => cx.stop_propagation())
            .on_click((_e, cx) => { cx.stop_propagation(); closeOverlay(p.overlay); })
            .child(glyph("close", 11)))
          .when(Boolean(command), el => el.child(div().id("toast-login-copy").px(5).py(2).rounded(4)
            .bg(t.raised).text_size(10).text_color(t.foreground).cursor_pointer()
            .on_mouse_down("left", (_e, cx) => cx.stop_propagation())
            .on_click((_e, cx) => { cx.stop_propagation(); cx.write_to_clipboard(command); this.copied = true; cx.notify(); })
            .child(this.copied ? "Copied" : "Copy")))
          .when(Boolean(p.action?.name) && !command, el => el.child(div().size(20).rounded(6)
            .flex().items_center().justify_center().bg(wash(color, 0.09)).text_color(color)
            .tooltip(isAgent ? "Open agent" : "Open").child(glyph("arrow", 12))))));
  }
}
