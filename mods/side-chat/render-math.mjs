import { randomUUID } from "node:crypto";
import { mkdir, readdir, rename, rm, stat, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { homedir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const tformula = join(homedir(), ".local/share/herdr-tformula/node_modules/tformula");
const require = createRequire(join(tformula, "package.json"));
const load = name => import(pathToFileURL(require.resolve(name)).href);
const loadTFormula = name => import(pathToFileURL(join(tformula, "dist", name)).href);

const [mode, root, token, source] = process.argv.slice(2);
if (!/^[a-f0-9]{32}$/.test(token)) throw new Error("Invalid side chat ID.");
const cache = join(root, "data", "side-chat-math");
const folder = join(cache, token);

if (mode === "clear") {
  await rm(folder, { recursive: true, force: true });
} else {
  console.log(JSON.stringify(await render(source)));
}

function visit(node, callback) {
  if (callback(node) === false) return;
  for (const child of node.children ?? []) visit(child, callback);
}

async function findMath(markdown) {
  const [{ fromMarkdown }, { gfm }, { gfmFromMarkdown }, { math }, { mathFromMarkdown }] = await Promise.all([
    load("mdast-util-from-markdown"), load("micromark-extension-gfm"), load("mdast-util-gfm"),
    load("micromark-extension-math"), load("mdast-util-math"),
  ]);
  const types = ["code", "inlineCode", "html", "link", "image", "definition"];
  const options = { extensions: [gfm(), math()], mdastExtensions: [gfmFromMarkdown(), mathFromMarkdown()] };
  const protectedRanges = [];
  visit(fromMarkdown(markdown, options), node => {
    if (!types.includes(node.type)) return;
    protectedRanges.push([node.position.start.offset, node.position.end.offset]);
    return false;
  });

  // Keep character offsets so the panel can preserve the original Markdown.
  let rangeIndex = 0;
  const normalized = markdown.replace(/(\\*)\\([()[\]])/g, (match, prefix, delimiter, start) => {
    while (protectedRanges[rangeIndex]?.[1] <= start) rangeIndex++;
    const range = protectedRanges[rangeIndex];
    if (prefix.length % 2 || (range && range[0] <= start)) return match;
    const replacement = { "(": "$ ", ")": " $", "[": "$$", "]": "$$" };
    return prefix + replacement[delimiter];
  });

  const formulas = [];
  for (const block of fromMarkdown(normalized, options).children) {
    visit(block, node => {
      if (types.includes(node.type)) return false;
      if (!["math", "inlineMath"].includes(node.type)) return;
      const { start, end } = node.position;
      const raw = markdown.slice(start.offset, end.offset);
      const parsed = normalized.slice(start.offset, end.offset).trimEnd();
      const fence = parsed.match(/^\$+/)?.[0];
      if (!fence || !node.value.trim() || !parsed.endsWith(fence)) return;
      if (raw.startsWith("\\(") !== raw.endsWith("\\)") || raw.startsWith("\\[") !== raw.trimEnd().endsWith("\\]")) return;
      if (fence === "$" && raw.startsWith("$")
          && (/\s/.test(raw[1]) || /\s/.test(raw.at(-2)) || /\d/.test(markdown[end.offset] ?? ""))) return;
      const display = fence.length > 1 || node.type === "math";
      const paragraph = !display && block.type === "paragraph"
        ? [block.position.start.offset, block.position.end.offset] : null;
      formulas.push({ start: start.offset, end: end.offset, latex: node.value.trim(), display, paragraph });
    });
  }
  return formulas;
}

async function render(markdown) {
  const formulas = await findMath(markdown);
  if (!formulas.length) return [];
  const [{ renderMathJaxSvg, readSvgDimensions }, { FormulaCache }] = await Promise.all([
    loadTFormula("math-renderer.js"), loadTFormula("formula-cache.js"),
  ]);
  const inMemory = new FormulaCache({ maxDiskBytes: 0 });
  await mkdir(folder, { recursive: true, mode: 0o700 });
  // A normal close clears these assets. Prune files left behind by a crash.
  for (const name of await readdir(cache)) {
    if (name === token || !/^[a-f0-9]{32}$/.test(name)) continue;
    const other = join(cache, name);
    const info = await stat(other).catch(() => null);
    if (info && Date.now() - info.mtimeMs > 24 * 60 * 60 * 1000) {
      await rm(other, { recursive: true, force: true });
    }
  }

  const rendered = [];
  for (const { latex, ...formula } of formulas.slice(0, 64)) {
    try {
      const svg = await renderMathJaxSvg(latex, formula.display, 360, inMemory);
      const { aspectRatio, heightEx } = readSvgDimensions(svg);
      const height = Math.ceil(heightEx * (formula.display ? 7.5 : 6.5));
      const width = Math.ceil(heightEx * aspectRatio * (formula.display ? 7.5 : 6.5));
      if (height > 600 || width > 3000) continue;
      const sized = svg.replace(/^<svg\b[^>]*>/, tag => tag
        .replace(/\bwidth="[^"]+"/, `width="${width}"`)
        .replace(/\bheight="[^"]+"/, `height="${height}"`));
      const name = randomUUID() + ".svg";
      const path = join(folder, name);
      await writeFile(path + ".tmp", sized, { mode: 0o600 });
      await rename(path + ".tmp", path);
      rendered.push({ ...formula, width, height, path: `data/side-chat-math/${token}/${name}` });
    } catch {
      // Leave the original Markdown in place when an equation cannot render.
    }
  }
  return rendered;
}
