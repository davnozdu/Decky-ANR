import { addEventListener, definePlugin, openFilePicker, FileSelectionType, removeEventListener, toaster } from "@decky/api";
import {
  ButtonItem,
  DropdownItem,
  Field,
  PanelSection,
  PanelSectionRow,
  Router,
  SliderField,
  ToggleField,
} from "@decky/ui";
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { MdAutoAwesome } from "react-icons/md";
import {
  AnrInfo,
  applyPathAll,
  BenchState,
  cancelBenchmark,
  checkUpdates,
  deleteBenchmarkKit,
  getBenchmark,
  getLegacyInfo,
  startBenchmark,
  GameEntry,
  GameStatus,
  getAnrInfo,
  getUiLanguage,
  getGameStatus,
  getPerformance,
  getUpscaler,
  getOptiSettings,
  setOptiSetting,
  copyProfile,
  resetProfile,
  setRenderQuality,
  setUpscaler,
  UpscalerInfo,
  PerfSession,
  installBundled,
  listGames,
  listOutdatedGames,
  patchGame,
  readGameLog,
  setActiveVersion,
  setGameSetting,
  setGeneratorMode,
  getLsfgStatus,
  installLsfg,
  importLsfgLibrary,
  refreshFsr4Dlls,
  getFsr4Library,
  importFsr4Libraries,
  extractFsr4Driver,
  Fsr4Library,
  LsfgProfile,
  LsfgStatus,
  unpatchGame,
  updateAllGames,
  updateFromGithub,
  UpdateInfo,
} from "./api";
import { t, translateMessage, initializeLanguage, subscribeLanguage, getLanguage } from "./i18n";
import { copyText, getLaunchOptions, setLaunchOptions } from "./steam";

declare const SteamClient: any;

const TITLE = "Decky FrameGen Hub";
const toast = (body: string) => toaster.toast({ title: TITLE, body: translateMessage(body) });
const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e));

const PATH_OPTIONS = ["auto", "coopmat", "packed", "dp4a", "portable", "portable-linalg", "portable-xmx"];
const AUTO_DIR = "__auto__";

const small: React.CSSProperties = { fontSize: "12px", lineHeight: "16px", opacity: 0.8, wordBreak: "break-word" };

let rememberedAppId = "";

// ─── ANR FG package section ──────────────────────────────────────────────────

declare const DeckyBackend: { call: (route: string, ...args: unknown[]) => Promise<unknown> };
const INSTALL_TYPE_UPDATE = 2;

const banner = (color: string): React.CSSProperties => ({
  ...small,
  opacity: 1,
  padding: "8px",
  borderRadius: "6px",
  background: color,
});

function PackageSection({ info, reload }: { info: AnrInfo | null; reload: () => Promise<void> }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [updates, setUpdates] = useState<UpdateInfo | null>(null);
  const [outdated, setOutdated] = useState<{ appid: string; name: string; version: string }[]>([]);

  const loadUpdates = useCallback(async (force: boolean) => {
    try {
      setUpdates(await checkUpdates(force));
    } catch (e) {
      setUpdates({ status: "error", message: errorText(e) });
    }
    try {
      setOutdated((await listOutdatedGames()).games || []);
    } catch {
      setOutdated([]);
    }
  }, []);

  useEffect(() => void loadUpdates(false), [loadUpdates, info?.version]);
  const [lsfg, setLsfg] = useState<LsfgStatus | null>(null);
  const loadLsfg = useCallback(async () => {
    try { setLsfg(await getLsfgStatus("")); } catch { setLsfg(null); }
  }, []);
  useEffect(() => void loadLsfg(), [loadLsfg]);

  const run = async (label: string, fn: () => Promise<{ status: string; message?: string }>) => {
    setBusy(label);
    try {
      const r = await fn();
      toast(r.message || (r.status === "success" ? t("Done.") : t("Failed.")));
    } catch (e) {
      toast(errorText(e));
    } finally {
      setBusy(null);
      await reload();
      await loadUpdates(false);
    }
  };

  const updatePlugin = async () => {
    if (!updates?.plugin_url) return;
    try {
      // Decky shows its own confirmation and reloads the plugin after installing.
      await DeckyBackend.call(
        "utilities/install_plugin",
        updates.plugin_url,
        TITLE,
        updates.plugin_latest,
        updates.plugin_hash || false,
        INSTALL_TYPE_UPDATE
      );
    } catch (e) {
      toast(t("Plugin update failed: {0}", errorText(e)));
    }
  };

  const checkedAt = updates?.checked_at ? new Date(updates.checked_at).toLocaleString(getLanguage() === "ru" ? "ru-RU" : "en-US") : null;

  return (
    <PanelSection title="ANR FG">
      {updates?.plugin_update && (
        <>
          <PanelSectionRow>
            <div style={banner("rgba(88,166,255,0.18)")}>
              <b>{TITLE} {updates.plugin_latest}</b> {" "}{t("is out (you have")}{" "}{updates.plugin_current}).
            </div>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={updatePlugin}>
              {" "}{t("Update the plugin to")}{" "}{updates.plugin_latest}
            </ButtonItem>
          </PanelSectionRow>
        </>
      )}

      {updates?.xefg_update && (
        <PanelSectionRow>
          <div style={banner("rgba(88,166,255,0.12)")}>
            <b>XeFG {updates.xefg_latest}</b> {" "}{t("is out (the plugin has")}{" "}{updates.xefg_current}{t("). XeFG builds are checked and pinned per plugin release: it arrives with the next plugin update.")}{" "}</div>
        </PanelSectionRow>
      )}

      {updates?.fsr4_update_games && updates.fsr4_update_games.length > 0 && (
        <>
          <PanelSectionRow>
            <div style={banner("rgba(255,216,102,0.12)")}>
              {" "}{t("Proton has a newer FSR 4 DLL (")}{updates.fsr4_latest}{t(") than")}{" "}{updates.fsr4_update_games.join(", ")}.
            </div>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy !== null} onClick={() => run("fsr4", refreshFsr4Dlls)}>
              {" "}{t("Update the FSR 4 DLL in these games")}{" "}</ButtonItem>
          </PanelSectionRow>
        </>
      )}

      {updates?.anr_update && (
        <PanelSectionRow>
          <div style={banner("rgba(255,216,102,0.18)")}>
            <b>{t("New ANR FG")}{" "}{updates.anr_latest}</b> {" "}{t("is out (you have")}{" "}{info?.version ?? t("not installed")}{t("). Download it below, then update your games.")}{" "}</div>
        </PanelSectionRow>
      )}

      <PanelSectionRow>
        <Field label={t("Package")} focusable>
          {info === null ? "…" : info.installed ? info.version : <span style={{ color: "#ffd866" }}>{t("not set up")}</span>}
        </Field>
      </PanelSectionRow>
      {!info?.installed && (
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy !== null} onClick={() => run("setup", installBundled)}>
            {busy === "setup" ? t("Setting up…") : t("Set up bundled ANR FG")}
          </ButtonItem>
        </PanelSectionRow>
      )}
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy !== null} onClick={() => run("update", updateFromGithub)}>
          {busy === "update"
            ? t("Downloading…")
            : updates?.anr_update
            ? t("Download ANR FG {0}", updates.anr_latest)
            : t("Get the newest release")}
        </ButtonItem>
      </PanelSectionRow>

      {outdated.length > 0 && (
        <>
          <PanelSectionRow>
            <div style={banner("rgba(255,216,102,0.12)")}>
              {outdated.length === 1 ? t("1 game uses") : t("{0} games use", outdated.length)} {" "}{t("an older ANR FG:")}{" "}
              {outdated.map((g) => `${g.name} (${g.version})`).join(", ")}
            </div>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy !== null} onClick={() => run("games", updateAllGames)}>
              {busy === "games" ? t("Updating games…") : t("Update {0} to {1}", outdated.length === 1 ? t("it") : t("all"), info?.version)}
            </ButtonItem>
          </PanelSectionRow>
        </>
      )}

      <PanelSectionRow>
        <Field label="Lossless Scaling (lsfg-vk)" focusable>
          {lsfg === null ? "…" : lsfg.installed ? lsfg.version : t("not installed")}
        </Field>
      </PanelSectionRow>
      {lsfg && lsfg.installed && lsfg.dll_state !== "ok" && (
        <PanelSectionRow>
          <div style={{ ...small, color: "#ffd866" }}>
            {lsfg.dll_state === "wrong_branch"
              ? t("Lossless Scaling is on its default branch, which lacks what lsfg-vk 2 needs. In Steam: Lossless Scaling → Properties → Betas → lsfg-vk.")
              : t("lsfg-vk needs your Lossless Scaling: install it from Steam and pick the beta branch \"lsfg-vk\" (Properties → Betas).")}
            {" "}{t("Or import your own lsfg-vk.dll or ZIP below.")}{" "}</div>
        </PanelSectionRow>
      )}
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy !== null}
          description={lsfg?.dll_state === "ok"
            ? lsfg.dll_source === "imported" ? t("Using your imported lsfg-vk.dll. Import a newer DLL or ZIP to update it.")
              : t("Using lsfg-vk.dll from your Steam library. You can also import your own file.")
            : t("Select lsfg-vk.dll from your own Lossless Scaling copy, or a ZIP containing it. Lossless.dll from the default branch is not compatible.")}
          onClick={async () => {
            let path: string;
            try {
              const file = await openFilePicker(FileSelectionType.FILE, lsfg?.home || "/home", true, true, undefined, ["dll", "zip"], false, false);
              path = file.realpath || file.path;
            } catch { return; }
            await run("lsfg-import", () => importLsfgLibrary(path));
            await loadLsfg();
          }}>
          {busy === "lsfg-import" ? t("Importing library…") : t("Import Lossless Scaling library (DLL / ZIP)")}
        </ButtonItem>
      </PanelSectionRow>
      {(!lsfg?.installed || updates?.lsfg_update) && (
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy !== null}
            onClick={async () => { await run("lsfg", installLsfg); await loadLsfg(); }}>
            {busy === "lsfg" ? t("Installing lsfg-vk…")
              : lsfg?.installed ? t("Update lsfg-vk to {0}", updates?.lsfg_latest) : t("Install lsfg-vk (frame generation for any game)")}
          </ButtonItem>
        </PanelSectionRow>
      )}

      {info?.versions && info.versions.length > 1 && (
        <PanelSectionRow>
          <DropdownItem
            label={t("Version for new patches")}
            selectedOption={info.version}
            rgOptions={[...info.versions].reverse().map((v) => ({ data: v, label: v }))}
            onChange={(o) => run("version", () => setActiveVersion(String(o.data)))}
          />
        </PanelSectionRow>
      )}

      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy !== null} onClick={() => run("check", async () => {
          const r = await checkUpdates(true);
          setUpdates(r);
          if (r.status !== "success") return r;
          const parts = [
            r.anr_update ? t("ANR FG {0} is out", r.anr_latest) : t("ANR FG: {0} is the newest", r.anr_latest ?? "?"),
            r.plugin_update ? t("plugin {0} is out", r.plugin_latest) : t("plugin is up to date"),
          ];
          return { status: "success", message: parts.join("; ") + (r.errors?.length ? ` (${r.errors.join("; ")})` : "") };
        })}>
          {busy === "check" ? t("Checking…") : t("Check for updates")}
        </ButtonItem>
      </PanelSectionRow>
      {checkedAt && (
        <PanelSectionRow>
          <div style={small}>
            {" "}{t("Checked")}{" "}{checkedAt}{t("; automatic check every 6 hours.")}{" "}{updates?.errors?.length ? t(" Last error: {0}", updates.errors[0]) : ""}
          </div>
        </PanelSectionRow>
      )}
    </PanelSection>
  );
}

// ─── Lossless Scaling (lsfg-vk) per-game controls ───────────────────────────

function LsfgControls({ profile, busy, onChange }: {
  profile: LsfgProfile | null; busy: boolean; onChange: (p: Partial<LsfgProfile>) => void;
}) {
  const m = profile?.multiplier ?? 2;
  const flow = Math.round((profile?.flow_scale ?? 1.0) * 100);
  return (
    <>
      <PanelSectionRow>
        <SliderField label={t("Lossless multiplier")} description={t("{0}X: {1} generated frame(s) per real frame.", m, m - 1)}
          value={m} min={2} max={4} step={1} showValue notchTicksVisible disabled={busy}
          onChange={(v: number) => onChange({ multiplier: v })} />
      </PanelSectionRow>
      <PanelSectionRow>
        <SliderField label={t("Flow scale")} description={t("Lower = faster, softer motion estimation (recommended 50–75% on handhelds).")}
          value={flow} min={25} max={100} step={5} showValue valueSuffix="%" disabled={busy}
          onChange={(v: number) => onChange({ flow_scale: v / 100 })} />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField label={t("Performance mode")} description={t("Lighter model: cheaper on the GPU, a little less accurate.")}
          checked={Boolean(profile?.performance_mode)} disabled={busy}
          onChange={(on: boolean) => onChange({ performance_mode: on })} />
      </PanelSectionRow>
      <PanelSectionRow>
        <div style={small}>
          {" "}{t("Turn the game's own frame generation off. Applies at the game's next start")}{profile?.active_in?.length ? ` (${profile.active_in.join(", ")})` : ""}.
        </div>
      </PanelSectionRow>
    </>
  );
}

// ─── Game section ────────────────────────────────────────────────────────────

function GameSection({ info }: { info: AnrInfo | null }) {
  const [games, setGames] = useState<GameEntry[]>([]);
  const [loadingGames, setLoadingGames] = useState(true);
  const [appid, setAppid] = useState<string>(() => rememberedAppId);
  const [status, setStatus] = useState<GameStatus | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(false);
  const [busy, setBusy] = useState<"patch" | "unpatch" | "generator" | null>(null);
  const [dirChoice, setDirChoice] = useState<string>(AUTO_DIR);
  const [log, setLog] = useState<string>("");
  const [perf, setPerf] = useState<{
    sessions: PerfSession[];
    summary?: { path: string; sessions: number; total_ms: number; real_fps: number | null }[];
  } | null>(null);
  const [launchOptions, setLaunchOptionsState] = useState<string>("");
  const [upscaler, setUpscalerInfo] = useState<UpscalerInfo | null>(null);
  const [opti, setOpti] = useState<Record<string, string>>({});
  const [copyFrom, setCopyFrom] = useState<string>("");

  const loadGames = useCallback(async () => {
    setLoadingGames(true);
    try {
      const r = await listGames();
      const list = (r.games || []).filter((g) => g.installed);
      setGames(list);
      setAppid((current) => {
        const running = String(Router.MainRunningApp?.appid ?? "");
        const pick =
          [current, running].find((id) => id && list.some((g) => g.appid === id)) || list[0]?.appid || "";
        rememberedAppId = pick;
        return pick;
      });
    } catch (e) {
      toast(errorText(e));
    } finally {
      setLoadingGames(false);
    }
  }, []);

  // silent: refresh after a settings change without disabling buttons, so the gamepad focus stays where it is.
  const loadStatus = useCallback(async (id: string, silent = false) => {
    if (!id) return setStatus(null);
    if (!silent) setLoadingStatus(true);
    try {
      setStatus(await getGameStatus(id));
      setLaunchOptionsState(await getLaunchOptions(Number(id)));
      try {
        setUpscalerInfo(await getUpscaler(id));
      } catch {
        setUpscalerInfo(null);
      }
      try {
        const o = await getOptiSettings(id);
        setOpti(o.status === "success" ? o.settings : {});
      } catch {
        setOpti({});
      }
    } catch (e) {
      setStatus({ status: "error", message: errorText(e) });
    } finally {
      if (!silent) setLoadingStatus(false);
    }
  }, []);

  useEffect(() => void loadGames(), [loadGames]);
  useEffect(() => {
    setDirChoice(AUTO_DIR);
    setLog("");
    setPerf(null);
    void loadStatus(appid);
  }, [appid, loadStatus]);

  const game = useMemo(() => games.find((g) => g.appid === appid) ?? null, [games, appid]);

  const doPatch = async () => {
    if (!game) return;
    setBusy("patch");
    try {
      const current = await getLaunchOptions(Number(appid));
      const r = await patchGame(appid, current, dirChoice === AUTO_DIR ? "" : dirChoice);
      if (r.status !== "success") throw new Error(r.message || t("Patch failed."));
      if (r.launch_options !== undefined && r.launch_options !== current) {
        setLaunchOptions(Number(appid), r.launch_options);
      }
      toast(r.message || t("Patched."));
    } catch (e) {
      toast(errorText(e));
    } finally {
      setBusy(null);
      await loadStatus(appid);
      await loadGames();
    }
  };

  const doUnpatch = async () => {
    if (!game) return;
    setBusy("unpatch");
    try {
      const current = await getLaunchOptions(Number(appid));
      const r = await unpatchGame(appid, current);
      if (r.status !== "success") throw new Error(r.message || t("Unpatch failed."));
      if (r.launch_options !== undefined && r.launch_options !== current) {
        setLaunchOptions(Number(appid), r.launch_options);
      }
      toast(r.message || t("Unpatched."));
    } catch (e) {
      toast(errorText(e));
    } finally {
      setBusy(null);
      await loadStatus(appid);
      await loadGames();
    }
  };

  const changeGenerator = async (choice: string, lsfg?: Partial<LsfgProfile>) => {
    setBusy("generator");
    setLog("");
    setPerf(null);
    const cur = { ...(status?.lsfg || { multiplier: 2, flow_scale: 1.0, performance_mode: false }), ...(lsfg || {}) };
    try {
      const r = await setGeneratorMode(appid, choice, cur.multiplier ?? 2, cur.flow_scale ?? 1.0, Boolean(cur.performance_mode));
      toast(r.message || r.status);
    } catch (e) {
      toast(errorText(e));
    } finally {
      setBusy(null);
      await loadStatus(appid, true);
    }
  };

  const changeSetting = async (key: string, value: string) => {
    try {
      const r = await setGameSetting(appid, key, value);
      toast(r.message || r.status);
    } catch (e) {
      toast(errorText(e));
    }
    await loadStatus(appid, true);
  };

  const changeUpscaler = async (choice: string, watermark: boolean) => {
    try {
      const r = await setUpscaler(appid, choice, watermark);
      toast(r.message || r.status);
    } catch (e) {
      toast(errorText(e));
    }
    await loadStatus(appid, true);
  };

  const changeOpti = async (key: string, value: string) => {
    const before = opti[key];
    setOpti((cur) => ({ ...cur, [key]: value }));
    let ok = false;
    try {
      const r = await setOptiSetting(appid, key, value);
      ok = r.status === "success";
      if (!ok) toast(r.message || t("Failed."));
      else if (r.message && (r.message.includes(t("Turned off")) || status?.running)) toast(r.message);
      if (ok) {
        // other settings may have been turned off with this one
        const o = await getOptiSettings(appid);
        if (o.status === "success") setOpti(o.settings);
      }
    } catch (e) {
      toast(errorText(e));
    }
    if (!ok) setOpti((cur) => ({ ...cur, [key]: before ?? "auto" }));
  };

  const profileAction = async (fn: () => Promise<{ status: string; message?: string }>) => {
    try {
      const r = await fn();
      toast(r.message || r.status);
    } catch (e) {
      toast(errorText(e));
    }
    await loadStatus(appid, true);
  };

  const changeRenderQuality = async (choice: string) => {
    try {
      const r = await setRenderQuality(appid, choice);
      toast(r.message || r.status);
    } catch (e) {
      toast(errorText(e));
    }
    await loadStatus(appid, true);
  };

  const renderSize = (ratio: number | null | undefined) => {
    const out = upscaler?.output || [1920, 1080];
    if (!ratio) return null;
    return `${Math.round(out[0] / ratio)}×${Math.round(out[1] / ratio)}`;
  };

  const addFfx4Upgrade = async () => {
    const current = await getLaunchOptions(Number(appid));
    if (current.includes("PROTON_FFX4_UPGRADE")) {
      toast(t("PROTON_FFX4_UPGRADE is already set: start the game once, then choose FSR 4."));
      return;
    }
    const next = current.includes("%command%")
      ? `PROTON_FFX4_UPGRADE=1 ${current}`
      : `PROTON_FFX4_UPGRADE=1 %command% ${current}`.trim();
    setLaunchOptions(Number(appid), next);
    toast(t("Added PROTON_FFX4_UPGRADE=1. Start the game once (proton-cachyos or GE-Proton), then choose FSR 4."));
    window.setTimeout(() => void loadStatus(appid, true), 500);
  };

  const showPerf = async () => {
    try {
      const r = await getPerformance(appid, 8);
      if (r.status !== "success") throw new Error(r.message || t("No data."));
      setPerf({ sessions: r.sessions || [], summary: r.summary });
      if (!r.sessions?.length) toast(t("No sessions with frame generation yet: play with DLSS FG on."));
    } catch (e) {
      toast(errorText(e));
    }
  };

  const showLog = async () => {
    try {
      const r = await readGameLog(appid, 30);
      setLog(r.log || r.message || "");
    } catch (e) {
      setLog(errorText(e));
    }
  };

  const patched = Boolean(status?.patched);
  const isXefg = status?.generator?.choice === "xefg";
  const genChoice = status?.generator?.choice || "anr";
  const generatorLabel =
    genChoice === "xefg" ? t("XeFG XMX Port · Build 10 beta")
    : genChoice === "lsfg" ? "Lossless Scaling (lsfg-vk)"
    : genChoice === "off" ? t("No frame generation")
    : genChoice === "custom" ? status?.generator?.provider || "custom"
    : "ANR FG";
  const proxyBase = (status?.proxy || "dxgi.dll").replace(/\.dll$/i, "");
  const anrLaunchLine = `WINEDLLOVERRIDES="${proxyBase}=n,b" %command%`;
  const launchHasOverride = launchOptions.includes(`${proxyBase}=n,b`);

  const copyLaunch = async () => {
    toast((await copyText(anrLaunchLine)) ? t("Copied: {0}", anrLaunchLine) : t("Could not copy to the clipboard."));
  };

  const applyLaunch = async () => {
    const current = await getLaunchOptions(Number(appid));
    const next = current.includes(`${proxyBase}=n,b`)
      ? current
      : current.includes("%command%")
      ? `WINEDLLOVERRIDES="${proxyBase}=n,b" ${current}`.trim()
      : `${anrLaunchLine} ${current}`.trim();
    setLaunchOptions(Number(appid), next);
    toast(t("Launch options: {0}", next));
    window.setTimeout(() => void loadStatus(appid, true), 500);
  };
  const outdated =
    patched && status?.game_version && status?.active_version && status.game_version !== status.active_version;
  const settings = status?.settings || {};
  const maxGenerated = Number(settings.max_generated || 1);

  const statusText = (() => {
    if (!game) return "—";
    if (loadingStatus) return "…";
    if (!status || status.status === "error") return status?.message || "—";
    if (!patched) return t("Not patched");
    const how = status.mode === "addon" ? t("add-on to OptiScaler") : t("OptiScaler as {0}", status.proxy);
    return t("{0} · ANR package {1} ({2})", generatorLabel, status.game_version ?? "?", how);
  })();

  return (
    <PanelSection title={t("Game")}>
      <PanelSectionRow>
        <DropdownItem
          layout="below"
          label={t("Steam game")}
          strDefaultLabel={loadingGames ? t("Loading…") : t("Choose a game")}
          disabled={loadingGames || games.length === 0}
          selectedOption={appid}
          rgOptions={games.map((g) => ({ data: g.appid, label: g.patched ? `★ ${g.name}` : g.name }))}
          onChange={(o) => {
            rememberedAppId = String(o.data);
            setAppid(String(o.data));
          }}
        />
      </PanelSectionRow>

      {game && (
        <>
          <PanelSectionRow>
            <Field label={t("Status")} focusable>
              <span style={{ color: patched ? (outdated ? "#ffd866" : "#3fb950") : undefined, fontWeight: 600 }}>
                {statusText}
              </span>
            </Field>
          </PanelSectionRow>

          {status?.proton && (
            <PanelSectionRow>
              <div style={{ ...small, color: status.proton.native ? "#ffd866" : undefined }}>
                {status.proton.native
                  ? t("Native Linux build (no .exe): ANR FG needs the Windows version under Proton.")
                  : `Proton: ${status.proton.tool ?? t("Steam default")}${
                      status.proton.source === "default" ? t(" (default)") : ""
                    }${status.proton.prefix ? t(", prefix {0}", status.proton.prefix) : ""}`}
              </div>
            </PanelSectionRow>
          )}

          {status?.running && (
            <PanelSectionRow>
              <div style={{ ...small, color: "#ffd866" }}>{t("The game is running: close it to patch or unpatch.")}</div>
            </PanelSectionRow>
          )}

          {patched && status?.target_rel && (
            <PanelSectionRow>
              <div style={small}>{t("Folder:")}{" "}{status.target_rel}</div>
            </PanelSectionRow>
          )}

          {!patched && status?.installed !== false && (
            <>
              <PanelSectionRow>
                <ToggleField
                  label={t("Lossless Scaling frame generation")}
                  description={t("lsfg-vk works in any game, also without DLSS Frame Generation. Needs your Lossless Scaling (Steam, branch lsfg-vk).")}
                  checked={Boolean(status?.lsfg)}
                  disabled={busy !== null || Boolean(status?.running)}
                  onChange={(on: boolean) => void changeGenerator(on ? "lsfg" : "off")}
                />
              </PanelSectionRow>
              {status?.lsfg && (
                <LsfgControls profile={status.lsfg} busy={busy !== null || Boolean(status?.running)}
                  onChange={(p) => void changeGenerator("lsfg", p)} />
              )}
            </>
          )}

          {!patched && status?.conflict && (
            <PanelSectionRow>
              <div style={{ ...small, color: "#ffd866" }}>{status.conflict}</div>
            </PanelSectionRow>
          )}

          {!patched && status?.candidates && status.candidates.length > 1 && (
            <PanelSectionRow>
              <DropdownItem
                layout="below"
                label={t("Game .exe")}
                selectedOption={dirChoice}
                rgOptions={[
                  { data: AUTO_DIR, label: t("Auto: {0}", status.candidates[0].exe) },
                  ...status.candidates.map((c) => ({ data: c.dir, label: c.exe })),
                ]}
                onChange={(o) => setDirChoice(String(o.data))}
              />
            </PanelSectionRow>
          )}

          <PanelSectionRow>
            <ButtonItem
              layout="below"
              disabled={!info?.installed || busy !== null || loadingStatus || status?.running}
              onClick={doPatch}
            >
              {busy === "patch"
                ? t("Installing…")
                : patched
                ? outdated
                  ? t("Update to {0}", status?.active_version)
                  : t("Reinstall ANR FG")
                : t("Install ANR FG")}
            </ButtonItem>
          </PanelSectionRow>

          {patched && (
            <PanelSectionRow>
              <ButtonItem
                layout="below"
                description={
                  status?.running
                    ? t("Close the game to remove it.")
                    : t("Restores the game's files and launch options; the game's profile is deleted.")
                }
                disabled={busy !== null || status?.running}
                onClick={doUnpatch}
              >
                {busy === "unpatch" ? t("Removing…") : t("Remove frame generation from this game")}
              </ButtonItem>
            </PanelSectionRow>
          )}

          {patched && (
            <PanelSectionRow>
              <div
                style={{
                  ...small,
                  opacity: 1,
                  padding: "8px",
                  borderRadius: "6px",
                  background: "rgba(63,185,80,0.12)",
                }}
              >
                <b>{t("Next steps")}</b>
                <br />
                {" "}{t("1. Start the game from Steam as usual.")}{" "}<br />
                {" "}{t("2. Graphics / Video settings: turn on Frame Generation and pick")}{" "}<b>DLSS Frame Generation</b> {" "}{t("(the NVIDIA option, not FSR).")}{" "}{generatorLabel} {" "}{t("takes its place.")}{" "}<br />
                {" "}{t("3. Turn in-game V-Sync off; limit FPS from the Steam menu if needed.")}{" "}<br />
                {" "}{t("4. Check it works: \"Show generator log\" below, or the FPS counter.")}{" "}</div>
            </PanelSectionRow>
          )}

          {patched && status?.mode === "full" && (
            <>
              <PanelSectionRow>
                <Field label={t("Launch options")} focusable bottomSeparator="none">
                  <span style={{ color: launchHasOverride ? "#3fb950" : "#ffd866" }}>
                    {launchHasOverride ? t("Set") : t("Missing")}
                  </span>
                </Field>
              </PanelSectionRow>
              <PanelSectionRow>
                <div style={small}>{launchOptions || t("(empty)")}</div>
              </PanelSectionRow>
              <PanelSectionRow>
                <ButtonItem layout="below" onClick={copyLaunch}>
                  {" "}{t("Copy launch options")}{" "}</ButtonItem>
              </PanelSectionRow>
              {!launchHasOverride && (
                <PanelSectionRow>
                  <ButtonItem layout="below" onClick={applyLaunch}>
                    {" "}{t("Apply launch options to the game")}{" "}</ButtonItem>
                </PanelSectionRow>
              )}
            </>
          )}


          {patched && (
            <>
              <PanelSectionRow>
                <DropdownItem
                  label={t("Frame generator")}
                  description={busy === "generator"
                    ? t("Preparing generator… First XeFG setup downloads about 75 MB.")
                    : t("Close the game to switch. XeFG is a beta for DirectX 12 games; Proton compatibility is experimental.")}
                  disabled={busy !== null || status?.running}
                  selectedOption={status?.generator?.choice || "anr"}
                  rgOptions={[
                    { data: "anr", label: "ANR FG" },
                    ...(status?.generator?.available !== false ? [{ data: "xefg", label: t("XeFG XMX Port · Build 10 (beta)") }] : []),
                    { data: "lsfg", label: "Lossless Scaling (lsfg-vk)" },
                    { data: "off", label: "Off" },
                    ...(status?.generator?.choice === "custom" ? [{ data: "custom", label: status.generator.provider }] : []),
                  ]}
                  onChange={(o) => { if (o.data !== "custom") void changeGenerator(String(o.data)); }}
                />
              </PanelSectionRow>
              {isXefg && (
                <PanelSectionRow>
                  <div style={small}>
                    {" "}{t("XeFG needs DirectX 12 and SDR or HDR10. Start with 2X. The ANR compute settings below are hidden; the frame multiplier and upscaler still apply.")}{" "}</div>
                </PanelSectionRow>
              )}
              {genChoice === "lsfg" && (
                <LsfgControls profile={status?.lsfg || null} busy={busy !== null || Boolean(status?.running)}
                  onChange={(p) => void changeGenerator("lsfg", p)} />
              )}
              {upscaler?.options && (
                <>
                  <PanelSectionRow>
                    <DropdownItem
                      label={t("Upscaler")}
                      description={
                        upscaler.choice === "fsr4lite"
                          ? t("INT8 Lite from your imported libraries. Enable the watermark to verify FSR4L-i8 after launch.")
                          : upscaler.choice === "fsr4"
                          ? t("FSR 4 {0} model{1}{2}", upscaler.rdna4 ? "FP8" : "INT8", upscaler.fsr4_source
                                ? t(", AMD FidelityFX {0} from {1}", upscaler.fsr4_source.version, upscaler.fsr4_source.source || "Proton")
                                : "", upscaler.gpu_family === "rdna2" ? t(". Slow on RDNA 2 (Steam Deck): FSR 3.1 is usually better.") : "")
                          : upscaler.gpu_family === "rdna2"
                          ? t("OptiScaler's upscaler. On RDNA 2 (Steam Deck) FSR 3.1 is the fast choice.")
                          : t("OptiScaler's upscaler. The game's DLSS option drives it.")
                      }
                      selectedOption={upscaler.choice || "package"}
                      rgOptions={upscaler.options.map((o) => ({
                        data: o.value,
                        label:
                          o.value === "fsr4lite" && !upscaler.fsr4_lite_available ? t("{0} (import ZIP first)", o.label)
                          : o.value === "fsr4" && !upscaler.fsr4_source ? t("{0} (needs Proton Experimental)", o.label)
                          : o.value === "fsr4" && upscaler.gpu_family === "rdna2" ? t("{0} · slow on this GPU", o.label)
                          : o.label,
                      }))}
                      onChange={(o) => void changeUpscaler(String(o.data), Boolean(upscaler.watermark))}
                    />
                  </PanelSectionRow>
                  {upscaler.render_options && (
                    <PanelSectionRow>
                      <DropdownItem
                        label={t("Render quality")}
                        description={(() => {
                          const cur = upscaler.render_options.find((o) => o.value === (upscaler.render_quality || "game"));
                          const out = upscaler.output || [1920, 1080];
                          return cur?.ratio
                            ? t("Renders at {0}, upscaled to {1}×{2}. Lower = faster.", renderSize(cur.ratio), out[0], out[1])
                            : t("Follows the DLSS mode chosen in the game (keep NVIDIA DLSS selected there).");
                        })()}
                        selectedOption={upscaler.render_quality || "game"}
                        rgOptions={upscaler.render_options.map((o) => ({
                          data: o.value,
                          label: o.ratio ? `${o.label} · ${renderSize(o.ratio)}` : o.label,
                        }))}
                        onChange={(o) => void changeRenderQuality(String(o.data))}
                      />
                    </PanelSectionRow>
                  )}
                  {!upscaler.fsr4_source && (
                    <>
                      {!upscaler.proton_experimental && (
                        <PanelSectionRow>
                          <ButtonItem layout="below"
                            description={t("Valve's Proton Experimental carries AMD's FSR 4 library; the plugin uses it from there.")}
                            onClick={() => {
                              try {
                                SteamClient.URL.ExecuteSteamURL("steam://install/1493710");
                              } catch {
                                toast(t("Install Proton Experimental from the Steam library (Tools)."));
                              }
                            }}>
                            {" "}{t("Install Proton Experimental (for FSR 4)")}{" "}</ButtonItem>
                        </PanelSectionRow>
                      )}
                      <PanelSectionRow>
                        <ButtonItem layout="below" onClick={addFfx4Upgrade}>
                          {" "}{t("Or: FSR 4 through proton-cachyos / GE-Proton (PROTON_FFX4_UPGRADE)")}{" "}</ButtonItem>
                      </PanelSectionRow>
                    </>
                  )}
                  {["fsr4", "fsr4lite"].includes(upscaler.choice || "") && (
                    <PanelSectionRow>
                      <ToggleField
                        label={t("Show the FSR watermark")}
                        description={t("Shows which FSR runs, to check FSR 4 is active.")}
                        checked={Boolean(upscaler.watermark)}
                        onChange={(on: boolean) => void changeUpscaler(upscaler.choice as string, on)}
                      />
                    </PanelSectionRow>
                  )}
                </>
              )}
              <PanelSectionRow>
                <div style={{ ...small, opacity: 1, fontWeight: 700, marginTop: "6px" }}>
                  {" "}{t("Game profile · tuning (OptiScaler). Close the game, change, start it again.")}{" "}</div>
              </PanelSectionRow>
              <PanelSectionRow>
                <DropdownItem
                  label={t("Frame generation multiplier")}
                  description={t("Overrides what the game asks for (many games only offer 2X on non-RTX 50 GPUs).")}
                  selectedOption={opti.fg_multiplier || "auto"}
                  rgOptions={[
                    { data: "auto", label: t("As the game asks") },
                    { data: "1", label: "2X" },
                    { data: "2", label: "3X" },
                    { data: "3", label: "4X" },
                    { data: "4", label: "5X" },
                    { data: "5", label: "6X" },
                  ]}
                  onChange={(o) => void changeOpti("fg_multiplier", String(o.data))}
                />
              </PanelSectionRow>
              <PanelSectionRow>
                <ToggleField
                  label={t("Dynamic multiplier (DMFG) · experimental")}
                  description={t("Picks the lowest multiplier that reaches the target FPS (Streamline 2.11 games). Caused a GPU hang in Forza Horizon 6 on a Radeon 890M while switching multipliers: prefer a fixed multiplier.")}
                  checked={opti.dynamic_mfg === "true"}
                  onChange={(on: boolean) => void changeOpti("dynamic_mfg", on ? "true" : "auto")}
                />
              </PanelSectionRow>
              {opti.dynamic_mfg === "true" && (
                <PanelSectionRow>
                  <SliderField
                    label={t("DMFG target FPS")}
                    description={t("0 = the display's refresh rate.")}
                    value={Number(opti.dmfg_target && opti.dmfg_target !== "auto" ? opti.dmfg_target : 0)}
                    min={0}
                    max={120}
                    step={10}
                    notchTicksVisible
                    showValue
                    onChange={(v: number) => void changeOpti("dmfg_target", String(v))}
                  />
                </PanelSectionRow>
              )}
              {opti.dynamic_mfg === "true" ? (
                <PanelSectionRow>
                  <div style={small}>{t("FPS limit and a fixed multiplier are off while Dynamic MFG holds its own target.")}</div>
                </PanelSectionRow>
              ) : (
              <PanelSectionRow>
                <SliderField
                  label={t("FPS limit")}
                  description={t("0 = off. FPS on screen, in steps of 10. Steadier pacing and less battery drain.")}
                  value={Number(opti.fps_limit && opti.fps_limit !== "auto" ? opti.fps_limit : 0)}
                  min={0}
                  max={120}
                  step={10}
                  notchTicksVisible
                  showValue
                  onChange={(v: number) => void changeOpti("fps_limit", String(v))}
                />
              </PanelSectionRow>
              )}
              <PanelSectionRow>
                <ToggleField
                  label={t("Sharpening (RCAS)")}
                  description={t("Override the sharpening strength; useful with Performance render quality.")}
                  checked={opti.sharpness_override === "true"}
                  onChange={(on: boolean) => void changeOpti("sharpness_override", on ? "true" : "auto")}
                />
              </PanelSectionRow>
              {opti.sharpness_override === "true" && (
                <PanelSectionRow>
                  <SliderField
                    label={t("Sharpening strength")}
                    value={Math.round(Number(opti.sharpness && opti.sharpness !== "auto" ? opti.sharpness : 0.3) * 10)}
                    min={0}
                    max={13}
                    step={1}
                    showValue
                    valueSuffix=" /10"
                    onChange={(v: number) => void changeOpti("sharpness", String(v / 10))}
                  />
                </PanelSectionRow>
              )}
              <PanelSectionRow>
                <ToggleField
                  label={t("OptiScaler FPS counter")}
                  checked={opti.show_fps === "true"}
                  onChange={(on: boolean) => void changeOpti("show_fps", on ? "true" : "auto")}
                />
              </PanelSectionRow>
              {games.filter((g) => g.patched && g.appid !== appid).length > 0 && (
                <>
                  <PanelSectionRow>
                    <DropdownItem
                      label={t("Copy the profile from")}
                      strDefaultLabel={t("Choose a game")}
                      selectedOption={copyFrom}
                      rgOptions={games
                        .filter((g) => g.patched && g.appid !== appid)
                        .map((g) => ({ data: g.appid, label: g.name }))}
                      onChange={(o) => setCopyFrom(String(o.data))}
                    />
                  </PanelSectionRow>
                  {copyFrom && (
                    <PanelSectionRow>
                      <ButtonItem layout="below" onClick={() => profileAction(() => copyProfile(appid, copyFrom))}>
                        {" "}{t("Copy the profile")}{" "}</ButtonItem>
                    </PanelSectionRow>
                  )}
                </>
              )}
              <PanelSectionRow>
                <ButtonItem layout="below" onClick={() => profileAction(() => resetProfile(appid))}>
                  {" "}{t("Reset the profile")}{" "}</ButtonItem>
              </PanelSectionRow>
              {genChoice === "anr" && (<>
              <PanelSectionRow>
                <SliderField
                  label={t("Generated frames")}
                  description={t("Up to {0}X. Restart the game after a change.", maxGenerated + 1)}
                  value={maxGenerated}
                  min={1}
                  max={5}
                  step={1}
                  showValue
                  notchTicksVisible
                  onChange={(v: number) => void changeSetting("max_generated", String(v))}
                />
              </PanelSectionRow>
              <PanelSectionRow>
                <DropdownItem
                  label={t("Compute path")}
                  selectedOption={settings.path || "auto"}
                  rgOptions={PATH_OPTIONS.map((p) => ({ data: p, label: p === "auto" ? t("Automatic") : p }))}
                  onChange={(o) => void changeSetting("path", String(o.data))}
                />
              </PanelSectionRow>
              <PanelSectionRow>
                <ToggleField
                  label={t("Scene cut detection")}
                  description={t("No interpolation across camera cuts.")}
                  checked={settings.scene_cut !== "0"}
                  onChange={(on: boolean) => void changeSetting("scene_cut", on ? "1" : "0")}
                />
              </PanelSectionRow>
              <PanelSectionRow>
                <ButtonItem layout="below" onClick={showPerf}>
                  {" "}{t("Performance by compute path")}{" "}</ButtonItem>
              </PanelSectionRow>
              {perf && perf.sessions.length > 0 && (
                <PanelSectionRow>
                  <div style={{ ...small, opacity: 1 }}>
                    {perf.summary && perf.summary.length > 0 && (
                      <div style={{ marginBottom: "6px" }}>
                        <b>{t("Best:")}</b> {perf.summary[0].path} ({perf.summary[0].total_ms} {" "}{t("ms GPU per real frame)")}{" "}{perf.summary.length > 1 &&
                          perf.summary
                            .slice(1)
                            .map((x) => t(" · {0} {1} ms", x.path, x.total_ms))
                            .join("")}
                      </div>
                    )}
                    <table style={{ width: "100%", borderCollapse: "collapse" }}>
                      <thead>
                        <tr style={{ textAlign: "left", opacity: 0.7 }}>
                          <th>{t("Path")}</th>
                          <th>{t("GPU ms")}</th>
                          <th>FPS</th>
                          <th>{t("Err")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {perf.sessions.map((x) => (
                          <tr key={x.log}>
                            <td>{x.path}</td>
                            <td>{x.total_ms ?? "—"}</td>
                            <td>
                              {x.real_fps ?? "—"}→{x.shown_fps ?? "—"}
                            </td>
                            <td style={{ color: x.errors ? "#ff7b72" : undefined }}>{x.errors}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <div style={{ marginTop: "6px", opacity: 0.7 }}>
                      {" "}{t("GPU ms: ANR's GPU time per real frame (pair + generated frames), lower is better. Newest session first. Compare paths in the same scene for a fair result.")}{" "}</div>
                  </div>
                </PanelSectionRow>
              )}
              </>)}
              <PanelSectionRow>
                <ButtonItem layout="below" onClick={showLog}>
                  {" "}{t("Show generator log")}{" "}</ButtonItem>
              </PanelSectionRow>
              {log && (
                <PanelSectionRow>
                  <pre style={{ ...small, whiteSpace: "pre-wrap", maxHeight: "240px", overflowY: "auto" }}>{log}</pre>
                </PanelSectionRow>
              )}
            </>
          )}

          <PanelSectionRow>
            <ButtonItem layout="below" disabled={loadingStatus} onClick={() => void loadStatus(appid)}>
              {" "}{t("Refresh")}{" "}</ButtonItem>
          </PanelSectionRow>
        </>
      )}
    </PanelSection>
  );
}

// ─── Benchmark (ANR FG test kit) ─────────────────────────────────────────────

const RUNNING_STAGES = ["starting", "download", "verify", "extract", "run"];

function BenchmarkSection() {
  const [bench, setBench] = useState<BenchState | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setBench(await getBenchmark());
    } catch (e) {
      setBench({ status: "error", message: errorText(e), live: {} });
    }
  }, []);

  const running = RUNNING_STAGES.includes(bench?.live?.stage || "");

  useEffect(() => void load(), [load]);
  useEffect(() => {
    if (!running) return undefined;
    const id = window.setInterval(() => void load(), 2000);
    return () => window.clearInterval(id);
  }, [running, load]);

  const stage = bench?.live?.stage;
  const lastStage = useRef<string | undefined>(undefined);
  useEffect(() => {
    const was = lastStage.current;
    lastStage.current = stage;
    if (!was || !RUNNING_STAGES.includes(was)) return;
    if (stage === "done") toast(bench?.live?.message || t("Benchmark finished."));
    if (stage === "error") toast(t("Benchmark: {0}", bench?.live?.message));
  }, [stage]);

  const act = async (fn: () => Promise<{ status: string; message?: string }>) => {
    setBusy(true);
    try {
      const r = await fn();
      if (r.message) toast(r.message);
    } catch (e) {
      toast(errorText(e));
    } finally {
      setBusy(false);
      await load();
    }
  };

  const result = bench?.live?.result || bench?.result || null;
  const live = bench?.live || {};
  const pct =
    live.total && live.total > 0 ? Math.min(100, Math.round(((live.progress || 0) / live.total) * 100)) : null;
  const sizes = result ? Object.keys(result.table).sort((a, b) => parseInt(a) - parseInt(b)) : [];
  const paths = result
    ? Array.from(new Set(sizes.flatMap((s) => Object.keys(result.table[s])))).sort((a, b) => {
        const ms = (p: string) => result.table[sizes[0]]?.[p]?.ms ?? 1e9;
        return ms(a) - ms(b);
      })
    : [];

  return (
    <PanelSection title={t("Benchmark")}>
      <PanelSectionRow>
        <div style={small}>
          {" "}{t("Runs ANR's official test kit on this GPU: every compute path at 1080p, 1440p and 4K, timed and checked against reference frames, next to AMD FSR 3.1 frame generation. Downloads ~570 MB once; takes 5–15 min. Close games first and plug the device in.")}{" "}</div>
      </PanelSectionRow>

      {running ? (
        <>
          <PanelSectionRow>
            <div style={{ ...small, opacity: 1 }}>
              {live.message}
              {pct !== null && (
                <div style={{ marginTop: "6px", height: "6px", borderRadius: "3px", background: "rgba(255,255,255,0.15)" }}>
                  <div style={{ width: `${pct}%`, height: "100%", borderRadius: "3px", background: "#58a6ff" }} />
                </div>
              )}
              {live.stage === "download" && live.total ? (
                <div style={{ marginTop: "4px" }}>
                  {Math.round((live.progress || 0) / 2 ** 20)} / {Math.round(live.total / 2 ** 20)} {" "}{t("MB")}{" "}</div>
              ) : null}
            </div>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy} onClick={() => act(cancelBenchmark)}>
              {" "}{t("Stop the benchmark")}{" "}</ButtonItem>
          </PanelSectionRow>
        </>
      ) : (
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={() => act(startBenchmark)}>
            {result ? t("Run the benchmark again") : t("Run the benchmark")}
          </ButtonItem>
        </PanelSectionRow>
      )}

      {live.stage === "error" && !running && (
        <PanelSectionRow>
          <div style={{ ...small, color: "#ff7b72" }}>{live.message}</div>
        </PanelSectionRow>
      )}

      {result && (
        <>
          <PanelSectionRow>
            <div style={{ ...small, opacity: 1 }}>
              <div style={{ marginBottom: "6px" }}>
                {result.gpu} · ANR {result.version} · {result.runs} {" "}{t("runs,")}{" "}{result.failed ?? 0} {" "}{t("failed")}{" "}</div>
              <div style={{ marginBottom: "6px" }}>
                <b>{t("Best:")}{" "}{result.best_path}</b>
                {result.auto_path && result.auto_path !== result.best_path
                  ? t(" (auto picks {0})", result.auto_path)
                  : result.auto_path
                  ? t(" (= auto)")
                  : ""}
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ textAlign: "left", opacity: 0.7 }}>
                    <th>{t("2X, ms · dB")}</th>
                    {sizes.map((s) => (
                      <th key={s}>{s}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {paths.map((p) => (
                    <tr key={p} style={{ fontWeight: p === result.best_path ? 700 : 400 }}>
                      <td>{p}</td>
                      {sizes.map((s) => {
                        const e = result.table[s]?.[p];
                        return (
                          <td key={s}>
                            {e?.ms ?? "—"}
                            {e?.db ? <span style={{ opacity: 0.6 }}> · {e.db}</span> : null}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                  {Object.keys(result.fsr || {}).length > 0 && (
                    <tr style={{ opacity: 0.8 }}>
                      <td>FSR 3.1 FG</td>
                      {sizes.map((s) => (
                        <td key={s}>{result.fsr[s] ?? "—"}</td>
                      ))}
                    </tr>
                  )}
                </tbody>
              </table>
              <div style={{ marginTop: "6px", opacity: 0.7 }}>
                {" "}{t("ms: GPU time per real frame at 2X, lower is better. dB: match to reference frames, higher is better.")}{" "}</div>
            </div>
          </PanelSectionRow>
          {result.best_path && (
            <PanelSectionRow>
              <ButtonItem
                layout="below"
                disabled={busy || running}
                onClick={() => act(() => applyPathAll(result.best_path as string))}
              >
                {bench?.preferred_path === result.best_path
                  ? t("{0} is applied (re-apply to all games)", result.best_path)
                  : t("Use {0} in all games", result.best_path)}
              </ButtonItem>
            </PanelSectionRow>
          )}
          {bench?.preferred_path && (
            <PanelSectionRow>
              <ButtonItem layout="below" disabled={busy || running} onClick={() => act(() => applyPathAll("auto"))}>
                {" "}{t("Back to auto in all games")}{" "}</ButtonItem>
            </PanelSectionRow>
          )}
        </>
      )}

      {!running && (bench?.kit_mb || 0) > 0 && (
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={() => act(deleteBenchmarkKit)}>
            {" "}{t("Delete the test kit (")}{bench?.kit_mb}{" "}{t("MB)")}
          </ButtonItem>
        </PanelSectionRow>
      )}
    </PanelSection>
  );
}

// ─── Help ────────────────────────────────────────────────────────────────────

function HelpSection() {
  return (
    <PanelSection title={t("How to use")}>
      <PanelSectionRow>
        <div style={small}>
          {" "}{t("1. Choose a game above and press Install ANR FG: the plugin sets the launch option WINEDLLOVERRIDES.")}{" "}<br />
          {" "}{t("2. Start the game. In its graphics settings turn on DLSS Frame Generation (the NVIDIA option, not FSR): ANR FG takes its place. Turn in-game V-Sync off.")}{" "}<br />
          {" "}{t("3. Works in D3D12 / Vulkan games that offer DLSS Frame Generation. OptiScaler's menu: Insert key.")}{" "}<br />
          {" "}{t("Games patched by Decky Framegen must be unpatched there first.")}{" "}</div>
      </PanelSectionRow>
    </PanelSection>
  );
}

function LegacyBanner() {
  const [legacy, setLegacy] = useState<{ installed: boolean; name: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try {
      const r = await getLegacyInfo();
      setLegacy({ installed: Boolean(r.legacy_installed), name: r.legacy_name || "Decky ANR" });
    } catch {
      setLegacy(null);
    }
  }, []);
  useEffect(() => void load(), [load]);
  if (!legacy?.installed) return null;
  const remove = async () => {
    setBusy(true);
    try {
      await DeckyBackend.call("utilities/uninstall_plugin", legacy.name);
      toast(t("{0} removed. Your game profiles were carried over.", legacy.name));
    } catch (e) {
      toast(errorText(e));
    } finally {
      setBusy(false);
      await load();
    }
  };
  return (
    <PanelSection title={t("Renamed")}>
      <PanelSectionRow>
        <div style={banner("rgba(88,166,255,0.18)")}>
          <b>{legacy.name}</b> {" "}{t("is now")}{" "}<b>{TITLE}</b>{t(". Your game profiles, ANR packages and XeFG files were carried over. Remove the old plugin so the two do not both manage the same games.")}{" "}</div>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy} onClick={remove}>
          {busy ? t("Removing…") : t("Remove the old {0} plugin", legacy.name)}
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}

function Fsr4Libraries({ onImported }: { onImported: () => void }) {
  const [library, setLibrary] = useState<Fsr4Library | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try { setLibrary(await getFsr4Library()); } catch (e) { toast(errorText(e)); }
  }, []);
  useEffect(() => void load(), [load]);
  const importFiles = async (kind: "driver" | "zip") => {
    let path: string;
    try {
      const file = await openFilePicker(FileSelectionType.FILE,
        library?.home || "/home", true, true, undefined,
        [kind === "driver" ? "exe" : "zip"], false, false);
      path = file.realpath || file.path;
    } catch { return; }
    setBusy(true);
    try {
      const result = await (kind === "driver" ? extractFsr4Driver(path)
        : importFsr4Libraries(path));
      toast(result.message || result.status);
      if (result.status === "success") { await load(); onImported(); }
    } catch (e) { toast(errorText(e)); }
    finally { setBusy(false); }
  };
  return (
    <PanelSection title={t("FSR 4 libraries")}>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy} onClick={() => void importFiles("driver")}
          description={library?.available
            ? t("Imported AMD library {0}. Select a newer driver to update. Closed games using Lite update automatically.", library.version)
            : t("Download an AMD Windows driver with FSR 4 Lite, then select its .exe here. Extracts and imports the libraries without installing the driver. Internet is needed only if portable 7-Zip is missing.")}>
          {busy ? t("Processing libraries… please wait") : t("Extract FSR 4 libraries from driver (.exe)")}
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy} onClick={() => void importFiles("zip")}
          description={t("Already extracted? Choose a ZIP containing amdxcffx64.dll and amdvkffx64.dll. For a new game, choose FSR 4 Lite in Upscaler after importing.")}>
          {" "}{t("Import libraries from ZIP")}{" "}</ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}

function Content() {
  const [fsrRevision, setFsrRevision] = useState(0);
  const [info, setInfo] = useState<AnrInfo | null>(null);
  const reload = useCallback(async () => {
    try {
      setInfo(await getAnrInfo());
    } catch (e) {
      toast(errorText(e));
    }
  }, []);
  useEffect(() => void reload(), [reload]);

  return (
    <>
      <LegacyBanner />
      <PackageSection info={info} reload={reload} />
      <Fsr4Libraries onImported={() => setFsrRevision((v) => v + 1)} />
      <GameSection key={fsrRevision} info={info} />
      <BenchmarkSection />
      <HelpSection />
    </>
  );
}

function LocalizedContent() {
  const language = useSyncExternalStore(subscribeLanguage, getLanguage, getLanguage);
  return <Content key={language} />;
}

export default definePlugin(() => {
  const stopLanguage = initializeLanguage(getUiLanguage);
  // The backend checks GitHub at start and every 6 hours and emits this once per new version.
  const onUpdate = (kind: string, version: string) => {
    const what: Record<string, string> = {
      plugin: t("{0} {1} is out: open the plugin to update.", TITLE, version),
      anr: t("ANR FG {0} is out: open {1} to download it.", version, TITLE),
      lsfg: t("lsfg-vk {0} is out: open {1} to update it.", version, TITLE),
      xefg: t("XeFG {0} is out: it comes with the next {1} update.", version, TITLE),
      fsr4: t("A newer FSR 4 DLL ({0}) is available: open {1} to update your games.", version, TITLE),
    };
    toast(what[kind] || t("{0} {1} is out.", kind, version));
  };
  const listener = addEventListener<[string, string]>("anr_update_available", onUpdate);
  return {
    name: TITLE,
    titleView: <div>{TITLE}</div>,
    content: <LocalizedContent />,
    icon: <MdAutoAwesome />,
    onDismount() {
      stopLanguage();
      removeEventListener("anr_update_available", listener);
    },
  };
});
