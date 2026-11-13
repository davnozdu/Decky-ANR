import { definePlugin, toaster } from "@decky/api";
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
import { useCallback, useEffect, useMemo, useState } from "react";
import { MdAutoAwesome } from "react-icons/md";
import {
  AnrInfo,
  GameEntry,
  GameStatus,
  getAnrInfo,
  getGameStatus,
  installBundled,
  listGames,
  patchGame,
  readGameLog,
  setActiveVersion,
  setGameSetting,
  unpatchGame,
  updateFromGithub,
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

function PackageSection({ info, reload }: { info: AnrInfo | null; reload: () => Promise<void> }) {
  const [busy, setBusy] = useState<string | null>(null);

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
    }
  };

  return (
    <PanelSection title="ANR FG">
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
          {busy === "update" ? "Checking GitHub…" : "Get the newest release"}
        </ButtonItem>
      </PanelSectionRow>
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
  const [launchOptions, setLaunchOptionsState] = useState<string>("");

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

  const loadStatus = useCallback(async (id: string) => {
    if (!id) return setStatus(null);
    setLoadingStatus(true);
    try {
      setStatus(await getGameStatus(id));
      setLaunchOptionsState(await getLaunchOptions(Number(id)));
    } catch (e) {
      setStatus({ status: "error", message: errorText(e) });
    } finally {
      setLoadingStatus(false);
    }
  }, []);

  useEffect(() => void loadGames(), [loadGames]);
  useEffect(() => {
    setDirChoice(AUTO_DIR);
    setLog("");
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
    await loadStatus(appid);
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
    window.setTimeout(() => void loadStatus(appid), 500);
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
            <PanelSectionRow>
              <ButtonItem layout="below" disabled={busy !== null || status?.running} onClick={doUnpatch}>
                {busy === "unpatch" ? "Removing…" : "Remove ANR FG"}
              </ButtonItem>
            </PanelSectionRow>
          )}

          {patched && (
            <>
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

// ─── Help ────────────────────────────────────────────────────────────────────

function HelpSection() {
  return (
    <PanelSection title="How to use">
      <PanelSectionRow>
        <div style={small}>
          1. Install ANR FG into a game: the plugin sets the launch option WINEDLLOVERRIDES for OptiScaler.
          <br />
          2. Start the game and turn on DLSS Frame Generation (the NVIDIA option): ANR FG takes its place.
          <br />
          3. OptiScaler's menu opens with Insert. Games need D3D12 or Vulkan with DLSS-G.
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
      <HelpSection />
    </>
  );
}

export default definePlugin(() => ({
  name: TITLE,
  titleView: <div>{TITLE}</div>,
  content: <Content />,
  icon: <MdAutoAwesome />,
  onDismount() {},
}));
