import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const helper = fileURLToPath(new URL("./render-math.mjs", import.meta.url));
const token = "a".repeat(32);

test("renders paired LaTeX while preserving code, currency, and invalid math", () => {
  const root = mkdtempSync(join(tmpdir(), "herdr-math-test-"));
  const run = (mode, ...args) => execFileSync(process.execPath, [helper, mode, root, token, ...args], { encoding: "utf8" });
  const markdown = [
    "π before $e^{i\\pi}+1=0$ and \\(x_1\\).",
    "",
    "$$",
    "\\frac{1}{2}",
    "$$",
    "",
    "\\[\\begin{pmatrix}1&0\\\\0&1\\end{pmatrix}\\]",
    "",
    "Prices are $20 or $30. Code says `$ignore$`.",
    "",
    "```latex",
    "\\[x^2\\]",
    "```",
    "",
    "$\\unrecognizedCommand{x}$",
    "",
    "$$",
    "unfinished",
  ].join("\n");
  try {
    const formulas = JSON.parse(run("render", markdown));
    assert.deepEqual(formulas.map(({ start, end }) => markdown.slice(start, end)), [
      "$e^{i\\pi}+1=0$", "\\(x_1\\)", "$$\n\\frac{1}{2}\n$$", "\\[\\begin{pmatrix}1&0\\\\0&1\\end{pmatrix}\\]",
    ]);
    assert.deepEqual(formulas.map(({ display }) => display), [false, false, true, true]);
    for (const { path, width, height } of formulas) {
      const svg = readFileSync(join(root, path), "utf8");
      assert.ok(width > 0 && height > 0);
      assert.match(svg, /^<svg\b/);
      assert.match(svg, /<path\b/);
    }
    run("clear");
    assert.throws(() => readFileSync(join(root, formulas[0].path)), { code: "ENOENT" });
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
