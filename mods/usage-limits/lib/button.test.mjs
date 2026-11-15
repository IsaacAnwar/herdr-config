import test from "node:test";
import assert from "node:assert/strict";
import { buttonModel, buttonChoices } from "./button.js";
import { effectivePrefs, selectButtonSource, toggleShowBars, toggleWindow } from "./prefs.js";

const at = 1000;
const states = {
  claude: { report: { status: "ok", windows: [
    { id: "session", long: "5-hour", percent: 20, resetsAt: 2000 },
    { id: "weekly_all", long: "Weekly", percent: 95, resetsAt: 3000 },
  ] } },
  codex: { report: { status: "ok", windows: [
    { id: "codex:primary", long: "5-hour", percent: 70, resetsAt: 2000 },
    { id: "codex:secondary", long: "Weekly", percent: 40, resetsAt: 3000 },
  ] } },
};

test("Claude five-hour is the default even when another allowance is lower", () => {
  const model = buttonModel(states, effectivePrefs(null), at);
  assert.equal(model.label, "Claude · 5-hour");
  assert.equal(model.text, "80%");
});

test("the chosen provider and exact window control the button", () => {
  const prefs = selectButtonSource(effectivePrefs(null), "codex", "codex:secondary");
  assert.equal(buttonModel(states, prefs, at).text, "60%");
  assert.equal(buttonModel(states, prefs, at).label, "Codex · Weekly");
});

test("selection survives saving and changing other usage preferences", () => {
  let prefs = selectButtonSource(effectivePrefs(null), "codex", "codex:primary");
  prefs = toggleWindow(toggleShowBars(prefs), "claude", "weekly_all");
  prefs = effectivePrefs(JSON.parse(JSON.stringify(prefs)));
  assert.deepEqual(prefs.buttonSource, { providerId: "codex", windowId: "codex:primary" });
  assert.equal(buttonModel(states, prefs, at).text, "30%");
});

test("missing or expired selected data never switches providers", () => {
  assert.equal(buttonModel({ codex: states.codex }, effectivePrefs(null), at).text, "—");
  assert.equal(buttonModel(states, effectivePrefs(null), 2100).text, "—");
  assert.equal(buttonModel(states, effectivePrefs(null), 2100).label, "Claude · 5-hour");
});

test("last good readings and all available window choices are supported", () => {
  const fallback = { claude: { report: { status: "error" }, lastGood: states.claude.report } };
  assert.equal(buttonModel(fallback, effectivePrefs(null), at).text, "80%");
  const choices = buttonChoices(states, effectivePrefs(null));
  assert.equal(choices.length, 4);
  assert.ok(choices.some(choice => choice.providerId === "claude" && choice.windowId === "weekly_all"));
  assert.ok(choices.some(choice => choice.providerId === "codex" && choice.windowId === "codex:primary"));
});
