import ru from "./locales/ru.json";

declare const SteamClient: any;
export type Language = "en" | "ru";
const catalog: Record<string, string> = ru;
export const normalizeLanguage = (value: unknown): Language => /^(ru(?:[-_]|$)|russian$)/i.test(String(value || "")) ? "ru" : "en";
let language = normalizeLanguage(typeof navigator === "undefined" ? "en" : navigator.language);
const subscribers = new Set<() => void>();
export const getLanguage = () => language;
export const subscribeLanguage = (fn: () => void) => { subscribers.add(fn); return () => { subscribers.delete(fn); }; };
export const setLanguage = (value: unknown) => {
  const next = normalizeLanguage(value);
  if (next !== language) { language = next; subscribers.forEach((fn) => fn()); }
};
export const t = (key: string, ...args: unknown[]): string =>
  (language === "ru" ? catalog[key] || key : key).replace(/\{(\d+)\}/g, (_, index) => String(args[Number(index)] ?? ""));

const escapeRegex = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const patterns = Object.keys(catalog).filter((s) => /\{\d+\}/.test(s))
  .sort((a, b) => b.replace(/\{\d+\}/g, "").length - a.replace(/\{\d+\}/g, "").length)
  .map((key) => {
    const indices: number[] = [];
    const pieces = key.split(/(\{\d+\})/g).map((part) => {
      if (/^\{\d+\}$/.test(part)) { indices.push(Number(part.slice(1, -1))); return "([\\s\\S]*?)"; }
      return escapeRegex(part);
    });
    return { key, regex: new RegExp("^" + pieces.join("") + "$"), indices };
  });

// Backends keep stable English messages and protocol enums. Only display text is localized here.
export function translateMessage(message: string, depth = 0): string {
  if (language !== "ru" || depth > 5 || !message) return message;
  if (message === "success") return t("Done.");
  if (message === "error") return t("Failed.");
  if (catalog[message]) return catalog[message];
  for (const p of patterns) {
    const match = p.regex.exec(message);
    if (match) {
      const args: string[] = [];
      p.indices.forEach((index, i) => { args[index] = translateMessage(match[i + 1], depth + 1); });
      return t(p.key, ...args);
    }
  }
  const trimmed = message.trim();
  if (trimmed !== message) {
    const result = translateMessage(trimmed, depth + 1);
    if (result !== trimmed) return message.slice(0, message.indexOf(trimmed)) + result + message.slice(message.indexOf(trimmed) + trimmed.length);
  }
  const sentences = message.split(/(?<=[.!?])\s+(?=[A-Z])/);
  if (sentences.length > 1) return sentences.map((s) => translateMessage(s, depth + 1)).join(" ");
  return message; // Keep unknown system/driver diagnostics readable and unchanged.
}

export function localizeResult<T>(value: T, field = ""): T {
  if (typeof value === "string") return (["message", "label", "conflict", "errors"].includes(field) ? translateMessage(value) : value) as T;
  if (Array.isArray(value)) return value.map((v) => localizeResult(v, field)) as T;
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, v]) => [key, localizeResult(v, key)])) as T;
  return value;
}

export function initializeLanguage(backendFallback: () => Promise<{ language?: string }>): () => void {
  let stopped = false;
  let pending = false;
  const refresh = async () => {
    if (pending) return;
    pending = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      const steam = typeof SteamClient !== "undefined" ? SteamClient?.Settings : undefined;
      let preferred: unknown;
      if (typeof steam?.GetCurrentLanguage === "function") {
        try {
          preferred = await Promise.race([steam.GetCurrentLanguage(), new Promise((resolve) => { timer = setTimeout(() => resolve(undefined), 1500); })]);
        } catch { /* Use Steam's saved config if its UI API is unavailable. */ }
      }
      if (!preferred) { try { preferred = (await backendFallback()).language; } catch { /* Browser locale is the last fallback. */ } }
      if (!stopped) setLanguage(preferred || (typeof navigator === "undefined" ? "en" : navigator.language));
    } finally { if (timer) clearTimeout(timer); pending = false; }
  };
  void refresh();
  const onLanguageChange = () => void refresh();
  window.addEventListener("languagechange", onLanguageChange);
  let registration: { unregister?: () => void } | undefined;
  try {
    if (typeof SteamClient !== "undefined") registration = SteamClient?.Settings?.RegisterForSettingsChanges?.(onLanguageChange);
  } catch { /* Older Steam clients may not expose the callback. */ }
  return () => { stopped = true; window.removeEventListener("languagechange", onLanguageChange); registration?.unregister?.(); };
}
