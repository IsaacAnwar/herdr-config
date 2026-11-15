import { level } from "./format.js";
import { PROVIDERS } from "../providers/index.js";

const defaultSource = { providerId: "claude", windowId: "session" };
const reportFor = state => state?.report?.status === "ok" ? state.report : state?.lastGood;
const matches = (a, b) => a.providerId === b.providerId && a.windowId === b.windowId;

export function buttonChoices(states, prefs, providers = PROVIDERS) {
  const choices = [];
  for (const provider of providers) {
    for (const window of reportFor(states[provider.id])?.windows ?? []) {
      choices.push({ providerId: provider.id, windowId: window.id, label: `${provider.name} · ${window.long}` });
    }
  }
  if (!choices.some(choice => matches(choice, defaultSource))) {
    choices.unshift({ ...defaultSource, label: "Claude · 5-hour" });
  }
  const selected = prefs?.buttonSource ?? defaultSource;
  if (!choices.some(choice => matches(choice, selected))) {
    const provider = providers.find(p => p.id === selected.providerId);
    choices.push({ ...selected, label: `${provider?.name ?? selected.providerId} · ${selected.windowId}` });
  }
  return choices;
}

export function buttonModel(states, prefs, at, providers = PROVIDERS) {
  const selected = prefs?.buttonSource ?? defaultSource;
  const choice = buttonChoices(states, prefs, providers).find(choice => matches(choice, selected));
  const window = reportFor(states[selected.providerId])?.windows?.find(window => window.id === selected.windowId);
  const available = Number.isFinite(window?.percent) && (window.resetsAt == null || window.resetsAt > at);
  const used = available ? window.percent : null;
  return { ...selected, label: choice.label, used,
    text: used == null ? "—" : `${Math.min(100, Math.max(0, 100 - used))}%`,
    level: used == null ? "ok" : level(used),
    hint: `${choice.label} remaining${available ? "" : " · waiting for a reading"}` };
}
