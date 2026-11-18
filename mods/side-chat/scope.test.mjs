import test from "node:test";
import assert from "node:assert/strict";
import { conversationKey, targetForFocus, SourceSelection, applySnapshot } from "./scope.js";

const source = (session, terminal = "t1") => ({ engine: "codex", session, terminal, title: session });
const pane = (terminal, tab, title = terminal) => ({ terminal, tab, title, app: "codex", cwd: "/project" });

test("Windows activity changes keep the same conversation target", () => {
  const focus = {space: "s", tab: "t", terminal: "t1"};
  const a = targetForFocus(focus, [pane("t1", "t", "[ . ] Working | Fix panels | user")], new Map());
  const b = targetForFocus(focus, [pane("t1", "t", "[ | ] Action Required | Fix panels | user")], new Map());
  assert.equal(a.stamp, b.stamp);
  const c = targetForFocus(focus, [pane("t1", "t", "Working | Different task | user")], new Map());
  assert.notEqual(a.stamp, c.stamp);
});

test("identity belongs to a provider conversation, independent of terminal or folder", () => {
  assert.equal(conversationKey(source("a", "t1")), conversationKey({ ...source("a", "t9"), cwd: "/other" }));
  assert.notEqual(conversationKey(source("a")), conversationKey(source("b")));
  assert.notEqual(conversationKey(source("a")), conversationKey({ ...source("a"), engine: "claude" }));
});

test("switching conversations within one space restores only the matching history, draft, and quote", () => {
  const remembered = new Map(), selection = new SourceSelection();
  const panes = [pane("t1", "tab-a"), pane("t2", "tab-b")];
  const a = targetForFocus({ space: "space", tab: "tab-a", terminal: "t1" }, panes, remembered);
  const b = targetForFocus({ space: "space", tab: "tab-b", terminal: "t2" }, panes, remembered);
  const chats = new Map([
    ["codex:a", { messages: ["private a"], draft: "draft a", quote: "quote a" }],
    ["codex:b", { messages: [], draft: "draft b", quote: "" }],
  ]);
  selection.accept(selection.begin(a.stamp), "codex:a");
  assert.equal(selection.owns(b), false);
  selection.accept(selection.begin(b.stamp), "codex:b");
  assert.deepEqual(chats.get(selection.key), { messages: [], draft: "draft b", quote: "" });
  selection.accept(selection.begin(a.stamp), "codex:a");
  assert.deepEqual(chats.get(selection.key), { messages: ["private a"], draft: "draft a", quote: "quote a" });
});

test("a reused terminal can select a new native conversation without inheriting the old one", () => {
  const selection = new SourceSelection();
  selection.accept(selection.begin("same-terminal"), "codex:old");
  selection.accept(selection.begin("same-terminal"), "codex:new");
  assert.equal(selection.key, "codex:new");
});

test("late source lookups cannot select a conversation after a tab switch", () => {
  const selection = new SourceSelection();
  const a = selection.begin("tab-a");
  const b = selection.begin("tab-b");
  assert.equal(selection.accept(b, "codex:b"), true);
  assert.equal(selection.accept(a, "codex:a"), false);
  assert.equal(selection.fail(a, "old error"), false);
  assert.equal(selection.key, "codex:b");
  const again = selection.begin("tab-a");
  assert.equal(selection.accept(a, "codex:a"), false);
  assert.equal(selection.accept(again, "codex:a"), true);
});

test("remembered focus stays within its tab and never guesses between split agents", () => {
  const remembered = new Map();
  const panes = [pane("t1", "a"), pane("t2", "b"), pane("t3", "b")];
  targetForFocus({ space: "s", tab: "a", terminal: "t1" }, panes, remembered);
  assert.equal(targetForFocus({ space: "s", tab: "b", terminal: null }, panes, remembered), null);
  targetForFocus({ space: "s", tab: "b", terminal: "t3" }, panes, remembered);
  assert.equal(targetForFocus({ space: "s", tab: "b", terminal: null }, panes, remembered).terminal, "t3");
  assert.equal(targetForFocus({ space: "s", tab: "b", terminal: "shell" }, panes, remembered), null);
});

test("a response for another conversation cannot overwrite the selected chat", () => {
  const chat = { key: "codex:a", source: source("a", "t9"), messages: ["original"], draft: "draft", quote: "quote" };
  assert.throws(() => applySnapshot(chat, { source: source("b"), messages: ["wrong"] }), /different conversation/);
  assert.deepEqual(chat.messages, ["original"]);
  applySnapshot(chat, { source: source("a", "t1"), messages: ["new answer"] });
  assert.equal(chat.source.terminal, "t9");
  assert.deepEqual(chat.messages, ["new answer"]);
  assert.equal(chat.draft, "draft");
  assert.equal(chat.quote, "quote");
});
