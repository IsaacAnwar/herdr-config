import { div, svg } from "gpui-kit";
import { h_flex, v_flex, TextView } from "gpui-base";
import { appHome, exec } from "herdr";

const mathByChat = new WeakMap();
const helper = () => `${appHome()}/mods/side-chat/render-math.mjs`;

async function renderMath(token, text) {
  const result = await exec("node", [helper(), "render", appHome(), token, text], { timeout: 12000 });
  return result.code === 0 ? JSON.parse(result.stdout) : [];
}

export function loadMath(chat, cx) {
  if (!chat?.token) return;
  let cache = mathByChat.get(chat);
  if (!cache) {
    cache = { token: chat.token, messages: new Map() };
    mathByChat.set(chat, cache);
  }
  if (cache.pending) return;
  for (const [index, { text }] of chat.messages.entries()) {
    if (chat.busy && index === chat.messages.length - 1) break;
    if (!text || text.length > 40000 || !/\$|\\[([]/.test(text) || cache.messages.get(index)?.text === text) continue;
    cache.pending = renderMath(cache.token, text)
      .catch(() => [])
      .then(formulas => cache.messages.set(index, { text, formulas }))
      .finally(() => { cache.pending = null; });
    cx.spawn(async cx => { await cache.pending; cx.notify(); });
    break;
  }
}

export async function clearMath(chat) {
  const cache = mathByChat.get(chat);
  if (!cache) return;
  await cache.pending;
  mathByChat.delete(chat);
  try { await exec("node", [helper(), "clear", appHome(), cache.token]); } catch (_) {}
}

function messageContent(id, text, color, formulas, maxWidth) {
  const markdown = (key, value) => TextView.markdown(`${id}-${key}`, value)
    .selectable(true).text_size(13).text_color(color);
  if (!formulas?.length) return markdown("text", text);
  const body = v_flex().gap(3).min_w(0);
  let cursor = 0;
  let row;
  let rowEnd = 0;
  const append = (target, start, end) => {
    const value = text.slice(start, end);
    if (value.trim()) target.child(markdown(start, value.trimEnd()).max_w(maxWidth));
  };
  for (const { start, end, display, paragraph, width, height, path } of formulas) {
    if (row && start >= rowEnd) {
      append(row, cursor, rowEnd);
      body.child(row);
      cursor = rowEnd;
      row = undefined;
    }
    if (paragraph && !row) {
      const [rowStart, endOfParagraph] = paragraph;
      append(body, cursor, rowStart);
      cursor = Math.max(cursor, rowStart);
      rowEnd = endOfParagraph;
      row = h_flex().w_full().flex_wrap().items_center();
    }
    append(row ?? body, cursor, start);
    const formula = div().id(`${id}-math-${start}`).flex_none().w(width).h(height)
      .cursor_copy().tooltip("Copy LaTeX")
      .on_click((_event, cx) => cx.write_to_clipboard(text.slice(start, end)))
      .child(svg(path).w(width).h(height).text_color(color));
    if (row && width <= maxWidth) {
      row.child(formula.ml(/\s/.test(text[start - 1] ?? "") ? 3 : 0)
        .mr(/\s/.test(text[end] ?? "") ? 3 : 0));
    } else {
      const frame = h_flex().id(`${id}-math-scroll-${start}`).w_full().min_w(0).py(display ? 6 : 2);
      if (width > maxWidth) frame.overflow_x_scrollbar();
      else if (display) frame.justify_center();
      frame.child(formula);
      (row ?? body).child(frame);
    }
    cursor = end;
  }
  if (row) {
    append(row, cursor, rowEnd);
    body.child(row);
    cursor = rowEnd;
  }
  append(body, cursor, text.length);
  return body;
}

export function chatMessage(chat, index, text, color, maxWidth) {
  const rendered = mathByChat.get(chat)?.messages.get(index);
  return messageContent(`side-message-${chat.token}-${index}`, text, color,
    rendered?.text === text ? rendered.formulas : null, maxWidth);
}
