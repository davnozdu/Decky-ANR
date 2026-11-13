// SteamClient helpers for reading and writing a game's launch options.

declare const SteamClient: any;

export const getLaunchOptions = (appId: number): Promise<string> =>
  new Promise((resolve) => {
    if (typeof SteamClient === "undefined" || !SteamClient?.Apps?.RegisterForAppDetails) {
      resolve("");
      return;
    }
    let settled = false;
    let unregister = () => {};
    const timeout = window.setTimeout(() => {
      if (settled) return;
      settled = true;
      unregister();
      resolve("");
    }, 5000);
    const registration = SteamClient.Apps.RegisterForAppDetails(
      appId,
      (details: { strLaunchOptions?: string }) => {
        if (settled) return;
        settled = true;
        window.clearTimeout(timeout);
        // Unregistering inside the callback can race the registration's return value.
        window.setTimeout(() => unregister(), 0);
        resolve(details?.strLaunchOptions ?? "");
      }
    );
    unregister = () => registration?.unregister?.();
  });

export const setLaunchOptions = (appId: number, options: string): void => {
  if (typeof SteamClient !== "undefined" && SteamClient?.Apps?.SetAppLaunchOptions) {
    SteamClient.Apps.SetAppLaunchOptions(appId, options);
  }
};

// Clipboard in Game Mode: execCommand on a hidden input works where navigator.clipboard often does not.
export const copyText = async (text: string): Promise<boolean> => {
  const input = document.createElement("input");
  input.value = text;
  input.style.position = "absolute";
  input.style.left = "-9999px";
  document.body.appendChild(input);
  try {
    input.focus();
    input.select();
    if (document.execCommand("copy")) return true;
  } catch {
    // fall through to the async clipboard API
  } finally {
    document.body.removeChild(input);
  }
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
};
