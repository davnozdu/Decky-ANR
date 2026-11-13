import { addEventListener, definePlugin, removeEventListener, toaster } from "@decky/api";
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
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MdAutoAwesome } from "react-icons/md";
import {
  AnrInfo,
  applyPathAll,
  BenchState,
  cancelBenchmark,
  checkUpdates,
  deleteBenchmarkKit,
  getBenchmark,
  startBenchmark,
  GameEntry,
  GameStatus,
  getAnrInfo,
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
  unpatchGame,
  updateAllGames,
  updateFromGithub,
  UpdateInfo,
} from "./api";
import { copyText, getLaunchOptions, setLaunchOptions } from "./steam";

const TITLE = "Decky ANR";
const toast = (body: string) => toaster.toast({ title: TITLE, body });
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

  const run = async (label: string, fn: () => Promise<{ status: string; message?: string }>) => {
    setBusy(label);
    try {
      const r = await fn();
      toast(r.message || (r.status === "success" ? "Done." : "Failed."));
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
        "Decky ANR",
        updates.plugin_latest,
        updates.plugin_hash || false,
        INSTALL_TYPE_UPDATE
      );
    } catch (e) {
      toast(`Plugin update failed: ${errorText(e)}`);
    }
  };

  const checkedAt = updates?.checked_at ? new Date(updates.checked_at).toLocaleString() : null;

  return (
    <PanelSection title="ANR FG">
      {updates?.plugin_update && (
        <>
          <PanelSectionRow>
            <div style={banner("rgba(88,166,255,0.18)")}>
              <b>Decky ANR {updates.plugin_latest}</b> is out (you have {updates.plugin_current}).
            </div>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={updatePlugin}>
              Update the plugin to {updates.plugin_latest}
            </ButtonItem>
          </PanelSectionRow>
        </>
      )}

      {updates?.anr_update && (
        <PanelSectionRow>
          <div style={banner("rgba(255,216,102,0.18)")}>
            <b>New ANR FG {updates.anr_latest}</b> is out (you have {info?.version ?? "none"}). Download it below,
            then update your games.
          </div>
        </PanelSectionRow>
      )}

      <PanelSectionRow>
        <Field label="Package" focusable>
          {info === null ? "…" : info.installed ? info.version : <span style={{ color: "#ffd866" }}>not set up</span>}
        </Field>
      </PanelSectionRow>
      {!info?.installed && (
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy !== null} onClick={() => run("setup", installBundled)}>
            {busy === "setup" ? "Setting up…" : "Set up bundled ANR FG"}
          </ButtonItem>
        </PanelSectionRow>
      )}
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy !== null} onClick={() => run("update", updateFromGithub)}>
          {busy === "update"
            ? "Downloading…"
            : updates?.anr_update
            ? `Download ANR FG ${updates.anr_latest}`
            : "Get the newest release"}
        </ButtonItem>
      </PanelSectionRow>

      {outdated.length > 0 && (
        <>
          <PanelSectionRow>
            <div style={banner("rgba(255,216,102,0.12)")}>
              {outdated.length === 1 ? "1 game uses" : `${outdated.length} games use`} an older ANR FG:{" "}
              {outdated.map((g) => `${g.name} (${g.version})`).join(", ")}
            </div>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy !== null} onClick={() => run("games", updateAllGames)}>
              {busy === "games" ? "Updating games…" : `Update ${outdated.length === 1 ? "it" : "all"} to ${info?.version}`}
            </ButtonItem>
          </PanelSectionRow>
        </>
      )}

      {info?.versions && info.versions.length > 1 && (
        <PanelSectionRow>
          <DropdownItem
            label="Version for new patches"
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
            r.anr_update ? `ANR FG ${r.anr_latest} is out` : `ANR FG: ${r.anr_latest ?? "?"} is the newest`,
            r.plugin_update ? `plugin ${r.plugin_latest} is out` : "plugin is up to date",
          ];
          return { status: "success", message: parts.join("; ") + (r.errors?.length ? ` (${r.errors.join("; ")})` : "") };
        })}>
          {busy === "check" ? "Checking…" : "Check for updates"}
        </ButtonItem>
      </PanelSectionRow>
      {checkedAt && (
        <PanelSectionRow>
          <div style={small}>
            Checked {checkedAt}; automatic check every 6 hours.
            {updates?.errors?.length ? ` Last error: ${updates.errors[0]}` : ""}
          </div>
        </PanelSectionRow>
      )}
    </PanelSection>
  );
}

// ─── Game section ────────────────────────────────────────────────────────────

function GameSection({ info }: { info: AnrInfo | null }) {
  const [games, setGames] = useState<GameEntry[]>([]);
  const [loadingGames, setLoadingGames] = useState(true);
  const [appid, setAppid] = useState<string>(() => rememberedAppId);
  const [status, setStatus] = useState<GameStatus | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(false);
  const [busy, setBusy] = useState<"patch" | "unpatch" | null>(null);
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
      if (r.status !== "success") throw new Error(r.message || "Patch failed.");
      if (r.launch_options !== undefined && r.launch_options !== current) {
        setLaunchOptions(Number(appid), r.launch_options);
      }
      toast(r.message || "Patched.");
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
      if (r.status !== "success") throw new Error(r.message || "Unpatch failed.");
      if (r.launch_options !== undefined && r.launch_options !== current) {
        setLaunchOptions(Number(appid), r.launch_options);
      }
      toast(r.message || "Unpatched.");
    } catch (e) {
      toast(errorText(e));
    } finally {
      setBusy(null);
      await loadStatus(appid);
      await loadGames();
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
      if (!ok) toast(r.message || "Failed.");
      else if (r.message && (r.message.includes("Turned off") || status?.running)) toast(r.message);
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
      toast("PROTON_FFX4_UPGRADE is already set: start the game once, then choose FSR 4.");
      return;
    }
    const next = current.includes("%command%")
      ? `PROTON_FFX4_UPGRADE=1 ${current}`
      : `PROTON_FFX4_UPGRADE=1 %command% ${current}`.trim();
    setLaunchOptions(Number(appid), next);
    toast("Added PROTON_FFX4_UPGRADE=1. Start the game once (proton-cachyos or GE-Proton), then choose FSR 4.");
    window.setTimeout(() => void loadStatus(appid, true), 500);
  };

  const showPerf = async () => {
    try {
      const r = await getPerformance(appid, 8);
      if (r.status !== "success") throw new Error(r.message || "No data.");
      setPerf({ sessions: r.sessions || [], summary: r.summary });
      if (!r.sessions?.length) toast("No sessions with frame generation yet: play with DLSS FG on.");
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
  const proxyBase = (status?.proxy || "dxgi.dll").replace(/\.dll$/i, "");
  const anrLaunchLine = `WINEDLLOVERRIDES="${proxyBase}=n,b" %command%`;
  const launchHasOverride = launchOptions.includes(`${proxyBase}=n,b`);

  const copyLaunch = async () => {
    toast((await copyText(anrLaunchLine)) ? `Copied: ${anrLaunchLine}` : "Could not copy to the clipboard.");
  };

  const applyLaunch = async () => {
    const current = await getLaunchOptions(Number(appid));
    const next = current.includes(`${proxyBase}=n,b`)
      ? current
      : current.includes("%command%")
      ? `WINEDLLOVERRIDES="${proxyBase}=n,b" ${current}`.trim()
      : `${anrLaunchLine} ${current}`.trim();
    setLaunchOptions(Number(appid), next);
    toast(`Launch options: ${next}`);
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
    if (!patched) return "Not patched";
    const how = status.mode === "addon" ? "add-on to OptiScaler" : `OptiScaler as ${status.proxy}`;
    return `ANR FG ${status.game_version ?? "?"} (${how})`;
  })();

  return (
    <PanelSection title="Game">
      <PanelSectionRow>
        <DropdownItem
          layout="below"
          label="Steam game"
          strDefaultLabel={loadingGames ? "Loading…" : "Choose a game"}
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
            <Field label="Status" focusable>
              <span style={{ color: patched ? (outdated ? "#ffd866" : "#3fb950") : undefined, fontWeight: 600 }}>
                {statusText}
              </span>
            </Field>
          </PanelSectionRow>

          {status?.proton && (
            <PanelSectionRow>
              <div style={{ ...small, color: status.proton.native ? "#ffd866" : undefined }}>
                {status.proton.native
                  ? "Native Linux build (no .exe): ANR FG needs the Windows version under Proton."
                  : `Proton: ${status.proton.tool ?? "Steam default"}${
                      status.proton.source === "default" ? " (default)" : ""
                    }${status.proton.prefix ? `, prefix ${status.proton.prefix}` : ""}`}
              </div>
            </PanelSectionRow>
          )}

          {status?.running && (
            <PanelSectionRow>
              <div style={{ ...small, color: "#ffd866" }}>The game is running: close it to patch or unpatch.</div>
            </PanelSectionRow>
          )}

          {patched && status?.target_rel && (
            <PanelSectionRow>
              <div style={small}>Folder: {status.target_rel}</div>
            </PanelSectionRow>
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
                label="Game .exe"
                selectedOption={dirChoice}
                rgOptions={[
                  { data: AUTO_DIR, label: `Auto: ${status.candidates[0].exe}` },
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
                ? "Installing…"
                : patched
                ? outdated
                  ? `Update to ${status?.active_version}`
                  : "Reinstall ANR FG"
                : "Install ANR FG"}
            </ButtonItem>
          </PanelSectionRow>

          {patched && (
            <PanelSectionRow>
              <ButtonItem
                layout="below"
                description={
                  status?.running
                    ? "Close the game to remove it."
                    : "Restores the game's files and launch options; the game's profile is deleted."
                }
                disabled={busy !== null || status?.running}
                onClick={doUnpatch}
              >
                {busy === "unpatch" ? "Removing…" : "Remove ANR FG from this game"}
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
                <b>Next steps</b>
                <br />
                1. Start the game from Steam as usual.
                <br />
                2. Graphics / Video settings: turn on Frame Generation and pick <b>DLSS Frame Generation</b> (the
                NVIDIA option, not FSR). ANR FG takes its place.
                <br />
                3. Turn in-game V-Sync off; limit FPS from the Steam menu if needed.
                <br />
                4. Check it works: "Show the newest nr_fg log" below, or the FPS counter.
              </div>
            </PanelSectionRow>
          )}

          {patched && status?.mode === "full" && (
            <>
              <PanelSectionRow>
                <Field label="Launch options" focusable bottomSeparator="none">
                  <span style={{ color: launchHasOverride ? "#3fb950" : "#ffd866" }}>
                    {launchHasOverride ? "set" : "missing"}
                  </span>
                </Field>
              </PanelSectionRow>
              <PanelSectionRow>
                <div style={small}>{launchOptions || "(empty)"}</div>
              </PanelSectionRow>
              <PanelSectionRow>
                <ButtonItem layout="below" onClick={copyLaunch}>
                  Copy launch options
                </ButtonItem>
              </PanelSectionRow>
              {!launchHasOverride && (
                <PanelSectionRow>
                  <ButtonItem layout="below" onClick={applyLaunch}>
                    Apply launch options to the game
                  </ButtonItem>
                </PanelSectionRow>
              )}
            </>
          )}


          {patched && (
            <>
              {upscaler?.options && (
                <>
                  <PanelSectionRow>
                    <DropdownItem
                      label="Upscaler"
                      description={
                        upscaler.choice === "fsr4"
                          ? `FSR 4 ${upscaler.rdna4 ? "FP8" : "INT8"} model${
                              upscaler.fsr4_source ? `, AMD FidelityFX ${upscaler.fsr4_source.version}` : ""
                            }`
                          : "OptiScaler's upscaler under ANR FG. The game's DLSS option drives it."
                      }
                      selectedOption={upscaler.choice || "package"}
                      rgOptions={upscaler.options.map((o) => ({
                        data: o.value,
                        label: o.value === "fsr4" && !upscaler.fsr4_source ? `${o.label} (needs setup)` : o.label,
                      }))}
                      onChange={(o) => void changeUpscaler(String(o.data), Boolean(upscaler.watermark))}
                    />
                  </PanelSectionRow>
                  {upscaler.render_options && (
                    <PanelSectionRow>
                      <DropdownItem
                        label="Render quality"
                        description={(() => {
                          const cur = upscaler.render_options.find((o) => o.value === (upscaler.render_quality || "game"));
                          const out = upscaler.output || [1920, 1080];
                          return cur?.ratio
                            ? `Renders at ${renderSize(cur.ratio)}, upscaled to ${out[0]}×${out[1]}. Lower = faster.`
                            : "Follows the DLSS mode chosen in the game (keep NVIDIA DLSS selected there).";
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
                    <PanelSectionRow>
                      <ButtonItem layout="below" onClick={addFfx4Upgrade}>
                        Get FSR 4 through Proton (PROTON_FFX4_UPGRADE)
                      </ButtonItem>
                    </PanelSectionRow>
                  )}
                  {upscaler.choice === "fsr4" && (
                    <PanelSectionRow>
                      <ToggleField
                        label="Show the FSR watermark"
                        description="Shows which FSR runs, to check FSR 4 is active."
                        checked={Boolean(upscaler.watermark)}
                        onChange={(on: boolean) => void changeUpscaler(upscaler.choice as string, on)}
                      />
                    </PanelSectionRow>
                  )}
                </>
              )}
              <PanelSectionRow>
                <div style={{ ...small, opacity: 1, fontWeight: 700, marginTop: "6px" }}>
                  Game profile · tuning (OptiScaler). Close the game, change, start it again.
                </div>
              </PanelSectionRow>
              <PanelSectionRow>
                <DropdownItem
                  label="Frame generation multiplier"
                  description="Overrides what the game asks for (many games only offer 2X on non-RTX 50 GPUs)."
                  selectedOption={opti.fg_multiplier || "auto"}
                  rgOptions={[
                    { data: "auto", label: "As the game asks" },
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
                  label="Dynamic multiplier (DMFG) · experimental"
                  description="Picks the lowest multiplier that reaches the target FPS (Streamline 2.11 games). Caused a GPU hang in Forza Horizon 6 on a Radeon 890M while switching multipliers: prefer a fixed multiplier."
                  checked={opti.dynamic_mfg === "true"}
                  onChange={(on: boolean) => void changeOpti("dynamic_mfg", on ? "true" : "auto")}
                />
              </PanelSectionRow>
              {opti.dynamic_mfg === "true" && (
                <PanelSectionRow>
                  <SliderField
                    label="DMFG target FPS"
                    description="0 = the display's refresh rate."
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
                  <div style={small}>FPS limit and a fixed multiplier are off while Dynamic MFG holds its own target.</div>
                </PanelSectionRow>
              ) : (
              <PanelSectionRow>
                <SliderField
                  label="FPS limit"
                  description="0 = off. FPS on screen, in steps of 10. Steadier pacing and less battery drain."
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
                  label="Sharpening (RCAS)"
                  description="Override the sharpening strength; useful with Performance render quality."
                  checked={opti.sharpness_override === "true"}
                  onChange={(on: boolean) => void changeOpti("sharpness_override", on ? "true" : "auto")}
                />
              </PanelSectionRow>
              {opti.sharpness_override === "true" && (
                <PanelSectionRow>
                  <SliderField
                    label="Sharpening strength"
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
                  label="OptiScaler FPS counter"
                  checked={opti.show_fps === "true"}
                  onChange={(on: boolean) => void changeOpti("show_fps", on ? "true" : "auto")}
                />
              </PanelSectionRow>
              {games.filter((g) => g.patched && g.appid !== appid).length > 0 && (
                <>
                  <PanelSectionRow>
                    <DropdownItem
                      label="Copy the profile from"
                      strDefaultLabel="Choose a game"
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
                        Copy the profile
                      </ButtonItem>
                    </PanelSectionRow>
                  )}
                </>
              )}
              <PanelSectionRow>
                <ButtonItem layout="below" onClick={() => profileAction(() => resetProfile(appid))}>
                  Reset the profile
                </ButtonItem>
              </PanelSectionRow>
              <PanelSectionRow>
                <SliderField
                  label="Generated frames"
                  description={`Up to ${maxGenerated + 1}X. Restart the game after a change.`}
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
                  label="Compute path"
                  selectedOption={settings.path || "auto"}
                  rgOptions={PATH_OPTIONS.map((p) => ({ data: p, label: p }))}
                  onChange={(o) => void changeSetting("path", String(o.data))}
                />
              </PanelSectionRow>
              <PanelSectionRow>
                <ToggleField
                  label="Scene cut detection"
                  description="No interpolation across camera cuts."
                  checked={settings.scene_cut !== "0"}
                  onChange={(on: boolean) => void changeSetting("scene_cut", on ? "1" : "0")}
                />
              </PanelSectionRow>
              <PanelSectionRow>
                <ButtonItem layout="below" onClick={showPerf}>
                  Performance by compute path
                </ButtonItem>
              </PanelSectionRow>
              {perf && perf.sessions.length > 0 && (
                <PanelSectionRow>
                  <div style={{ ...small, opacity: 1 }}>
                    {perf.summary && perf.summary.length > 0 && (
                      <div style={{ marginBottom: "6px" }}>
                        <b>Best:</b> {perf.summary[0].path} ({perf.summary[0].total_ms} ms GPU per real frame)
                        {perf.summary.length > 1 &&
                          perf.summary
                            .slice(1)
                            .map((x) => ` · ${x.path} ${x.total_ms} ms`)
                            .join("")}
                      </div>
                    )}
                    <table style={{ width: "100%", borderCollapse: "collapse" }}>
                      <thead>
                        <tr style={{ textAlign: "left", opacity: 0.7 }}>
                          <th>Path</th>
                          <th>GPU ms</th>
                          <th>FPS</th>
                          <th>Err</th>
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
                      GPU ms: ANR's GPU time per real frame (pair + generated frames), lower is better. Newest
                      session first. Compare paths in the same scene for a fair result.
                    </div>
                  </div>
                </PanelSectionRow>
              )}
              <PanelSectionRow>
                <ButtonItem layout="below" onClick={showLog}>
                  Show the newest nr_fg log
                </ButtonItem>
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
              Refresh
            </ButtonItem>
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
    if (stage === "done") toast(bench?.live?.message || "Benchmark finished.");
    if (stage === "error") toast(`Benchmark: ${bench?.live?.message}`);
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
    <PanelSection title="Benchmark">
      <PanelSectionRow>
        <div style={small}>
          Runs ANR's official test kit on this GPU: every compute path at 1080p, 1440p and 4K, timed and checked against
          reference frames, next to AMD FSR 3.1 frame generation. Downloads ~570 MB once; takes 5–15 min. Close games
          first and plug the device in.
        </div>
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
                  {Math.round((live.progress || 0) / 2 ** 20)} / {Math.round(live.total / 2 ** 20)} MB
                </div>
              ) : null}
            </div>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy} onClick={() => act(cancelBenchmark)}>
              Stop the benchmark
            </ButtonItem>
          </PanelSectionRow>
        </>
      ) : (
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={() => act(startBenchmark)}>
            {result ? "Run the benchmark again" : "Run the benchmark"}
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
                {result.gpu} · ANR {result.version} · {result.runs} runs, {result.failed ?? 0} failed
              </div>
              <div style={{ marginBottom: "6px" }}>
                <b>Best: {result.best_path}</b>
                {result.auto_path && result.auto_path !== result.best_path
                  ? ` (auto picks ${result.auto_path})`
                  : result.auto_path
                  ? " (= auto)"
                  : ""}
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ textAlign: "left", opacity: 0.7 }}>
                    <th>2X, ms · dB</th>
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
                ms: GPU time per real frame at 2X, lower is better. dB: match to reference frames, higher is better.
              </div>
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
                  ? `${result.best_path} is applied (re-apply to all games)`
                  : `Use ${result.best_path} in all games`}
              </ButtonItem>
            </PanelSectionRow>
          )}
          {bench?.preferred_path && (
            <PanelSectionRow>
              <ButtonItem layout="below" disabled={busy || running} onClick={() => act(() => applyPathAll("auto"))}>
                Back to auto in all games
              </ButtonItem>
            </PanelSectionRow>
          )}
        </>
      )}

      {!running && (bench?.kit_mb || 0) > 0 && (
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={() => act(deleteBenchmarkKit)}>
            Delete the test kit ({bench?.kit_mb} MB)
          </ButtonItem>
        </PanelSectionRow>
      )}
    </PanelSection>
  );
}

// ─── Help ────────────────────────────────────────────────────────────────────

function HelpSection() {
  return (
    <PanelSection title="How to use">
      <PanelSectionRow>
        <div style={small}>
          1. Choose a game above and press Install ANR FG: the plugin sets the launch option WINEDLLOVERRIDES.
          <br />
          2. Start the game. In its graphics settings turn on DLSS Frame Generation (the NVIDIA option, not FSR):
          ANR FG takes its place. Turn in-game V-Sync off.
          <br />
          3. Works in D3D12 / Vulkan games that offer DLSS Frame Generation. OptiScaler's menu: Insert key.
          <br />
          Games patched by Decky Framegen must be unpatched there first.
        </div>
      </PanelSectionRow>
    </PanelSection>
  );
}

function Content() {
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
      <PackageSection info={info} reload={reload} />
      <GameSection info={info} />
      <BenchmarkSection />
      <HelpSection />
    </>
  );
}

export default definePlugin(() => {
  // The backend checks GitHub at start and every 6 hours and emits this once per new version.
  const onUpdate = (kind: string, version: string) => {
    toast(
      kind === "plugin"
        ? `Decky ANR ${version} is out: open the plugin to update.`
        : `ANR FG ${version} is out: open Decky ANR to download it.`
    );
  };
  const listener = addEventListener<[string, string]>("anr_update_available", onUpdate);
  return {
    name: TITLE,
    titleView: <div>{TITLE}</div>,
    content: <Content />,
    icon: <MdAutoAwesome />,
    onDismount() {
      removeEventListener("anr_update_available", listener);
    },
  };
});
