// Original ASCII scenes rendered offline and played by Herdr's native image renderer.
export const THEMES_KEY = "side-chat.appearance";
export const THEMES = [
  { id: "orbit", name: "Orbit", style: "Orbital" },
  { id: "dunes", name: "Dunes", style: "Contours" },
  { id: "tide", name: "Tide", style: "Contours" },
  { id: "fish", name: "Koi", style: "Pond" },
  { id: "stars", name: "Stars", style: "Meteor shower" },
  { id: "fireflies", name: "Fireflies", style: "Meadow" },
  { id: "rain", name: "Rain", style: "Classic" },
  { id: "garden", name: "Garden", style: "Botanical" },
  { id: "herdr", name: "None", style: "No artwork" },
];

export function appearanceFor(saved, space) {
  const prefs = saved?.[space] ?? {};
  const choice = prefs.theme === "ripples" ? "fireflies" : prefs.theme;
  return { theme: THEMES.some(t => t.id === choice) ? choice : "orbit", color: prefs.color !== false };
}

export function changeAppearance(saved, space, change) {
  return { ...(saved ?? {}), [space]: { ...appearanceFor(saved, space), ...change } };
}

export function sceneAsset(id, mode = "animated", background = "#202328", color = false) {
  if (id === "herdr" || !THEMES.some(t => t.id === id)) return null;
  const value = parseInt(background.slice(1, 7), 16);
  const brightness = ((value >> 16) & 255) * 0.2126 + ((value >> 8) & 255) * 0.7152 + (value & 255) * 0.0722;
  const variant = brightness < 128 ? "dark" : "light";
  const suffix = mode === "animated" ? "" : `-${mode}`;
  return `mods/side-chat/assets/${id === "fish" ? "pond" : id}-${variant}${color ? "-color" : ""}${suffix}.webp`;
}
