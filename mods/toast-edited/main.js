import { View, div, image, svg } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { props, closeOverlay, run, theme, terminals } from "herdr";

const glyph = (name, size = 14) => svg(`mods/my-toast/${name}.svg`).size(size).flex_none();

export default class Toast extends View {
  render() {
    const t = theme(), p = props() ?? {};
    const isAgent = p.action?.name === "agent.focus";
    const finished = isAgent && /finished$/i.test(p.title ?? "");
    const needsYou = isAgent && /needs you$/i.test(p.title ?? "");
    const terminal = isAgent ? terminals().find(a => a.address === p.action.args?.terminal) : null;
    const program = terminal?.program;
    const color = finished || p.level === "success" ? t.ansi2 : needsYou || p.level === "warning" ? t.ansi3 : p.level === "error" ? t.ansi1 : t.accent;
    const status = finished ? "Task complete" : needsYou ? "Needs your attention" : p.level === "error" ? "Something went wrong" : p.level === "success" ? "Complete" : "Notification";
    const title = isAgent ? (p.title ?? "Agent").replace(/\s+(finished|needs you)$/i, "") : p.title ?? "Herdr";
    const dismiss = (_e, cx) => { cx.stop_propagation(); closeOverlay(p.overlay); };
    const open = () => {
      if (p.action?.name) run(p.action.name, p.action.args ?? {});
      closeOverlay(p.overlay);
    };
    const picture = program?.icon
      ? (program.tint ? svg(program.icon).size(19).text_color(t.foreground) : image(program.icon).size(19))
      : p.icon ? image(p.icon).size(19) : glyph(finished || p.level === "success" ? "check" : needsYou || p.level === "error" ? "alert" : "bell", 18).text_color(color);
    return h_flex().id("toast").size_full().rounded(11).overflow_hidden().border_1().border_color(t.border)
      .bg(t.popover).shadow_lg().cursor_pointer().hover(s => s.bg(t.raised)).on_click(open)
      .tooltip([p.title, p.body, p.action?.name ? "Click to open" : null].filter(Boolean).join("\n"))
      .child(div().w(3).h_full().flex_none().bg(color))
      .child(h_flex().flex_1().min_w(0).px(12).gap(10).items_center()
        .child(div().relative().size(32).rounded(9).flex_none().flex().items_center().justify_center()
          .bg(t.raised).border_1().border_color(t.border).child(picture)
          .when(Boolean(program?.icon) && finished, e => e.child(div().absolute().right(-2).bottom(-2).size(12).rounded(6)
            .bg(color).border(2).border_color(t.popover).flex().items_center().justify_center()
            .child(glyph("check", 7).text_color(t.background)))))
        .child(v_flex().flex_1().min_w(0).gap(2)
          .child(div().text_size(9.5).font_semibold().text_color(color).child(status))
          .child(div().truncate().font_semibold().text_size(12.5).text_color(t.foreground).child(title))
          .when(Boolean(p.body), e => e.child(div().truncate().text_size(10.5).text_color(t.muted).child(p.body))))
        .child(v_flex().gap(5).flex_none().items_center()
          .child(div().id("toast-dismiss").size(18).rounded(4).flex().items_center().justify_center().text_color(t.dim)
            .hover(s => s.bg(t.hover).text_color(t.foreground)).tooltip("Dismiss")
            .on_mouse_down("left", (_e, cx) => cx.stop_propagation()).on_click(dismiss).child(glyph("close", 11)))
          .when(Boolean(p.action?.name), e => e.child(div().id("toast-open").size(18).rounded(4).flex().items_center().justify_center().text_color(t.muted)
            .tooltip(isAgent ? "Open agent" : "Open").child(glyph("arrow", 12))))));
  }
}
