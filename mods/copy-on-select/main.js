import { View, div } from "gpui-kit";
import { focused, run, exec, props, closeOverlay } from "herdr";

const DRAG_PX = 4;

const WAIT_FOR_RELEASE =
  'ObjC.import("AppKit"); var t = 0;' +
  " while (($.NSEvent.pressedMouseButtons & 1) && t < 3000) { delay(0.02); t++; }" +
  ' "up"';

export default class CopyOnSelect extends View {
  init() {
    this.press = 0;
    // Dismiss a popup still open when this mod hot-reloads.
    if (props()?.toast) closeOverlay(props().overlay);
  }

  start(event, cx) {
    if (event.button !== "left") return;
    const m = event.modifiers;
    if (m.platform || m.control || m.alt) return;

    const press = ++this.press;
    const down = event.position;
    const multiClick = event.click_count >= 2;
    let dragged = false;

    const watch = cx.timer.every(40, () => {
      const p = window.mouse_position();
      if (Math.abs(p.x - down.x) > DRAG_PX || Math.abs(p.y - down.y) > DRAG_PX) dragged = true;
    });

    cx.spawn(async () => {
      try {
        await exec("osascript", ["-l", "JavaScript", "-e", WAIT_FOR_RELEASE]);
      } catch (_) {}
      watch.cancel();
      if (press !== this.press) return;
      const p = window.mouse_position();
      if (Math.abs(p.x - down.x) > DRAG_PX || Math.abs(p.y - down.y) > DRAG_PX) dragged = true;
      if (!(dragged || multiClick)) return;
      if (!focused()?.terminal) return;
      run("terminal.copy");
    });
  }

  render(_cx) {
    return div()
      .id("copy-on-select")
      .size_full()
      .on_mouse_down_out((event, cx) => this.start(event, cx));
  }
}
