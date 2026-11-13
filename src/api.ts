import { callable } from "@decky/api";

export type Result = { status: "success" | "error"; message?: string; output?: string };

export type AnrInfo = Result & {
  installed?: boolean;
  version?: string | null;
  versions?: string[];
  built_at?: string | null;
  optiscaler?: string | null;
};

export type GameEntry = { appid: string; name: string; installed: boolean; patched: boolean };

export type Candidate = { dir: string; exe: string };

export type GameStatus = Result & {
  appid?: string;
  name?: string;
  installed?: boolean;
  patched?: boolean;
  mode?: "full" | "addon" | null;
  proxy?: string | null;
  target_dir?: string;
  target_rel?: string;
  game_version?: string | null;
  active_version?: string | null;
  settings?: Record<string, string | null>;
  log_file?: string | null;
  candidates?: Candidate[];
  suggested_dir?: string;
  conflict?: string | null;
  running?: boolean;
  proton?: { tool: string | null; source: "game" | "default"; prefix: string | null; native: boolean };
};

export type PatchResult = Result & { launch_options?: string; mode?: string; proxy?: string | null };

export const getAnrInfo = callable<[], AnrInfo>("get_anr_info");
export const installBundled = callable<[], Result & { version?: string }>("install_bundled");
export const updateFromGithub = callable<[], Result & { version?: string }>("update_from_github");
export const setActiveVersion = callable<[version: string], Result>("set_active_version");
export const listGames = callable<[], Result & { games: GameEntry[] }>("list_games");
export const getGameStatus = callable<[appid: string], GameStatus>("get_game_status");
export const patchGame = callable<
  [appid: string, current_launch_options: string, target_dir: string],
  PatchResult
>("patch_game");
export const unpatchGame = callable<[appid: string, current_launch_options: string], PatchResult>(
  "unpatch_game"
);
export const setGameSetting = callable<[appid: string, key: string, value: string], Result>(
  "set_game_setting"
);
export const readGameLog = callable<[appid: string, lines: number], Result & { log?: string; path?: string }>(
  "read_game_log"
);
export const logError = callable<[string], void>("log_error");

export type UpdateInfo = Result & {
  checked_at?: string;
  errors?: string[];
  anr_latest?: string | null;
  anr_update?: boolean;
  anr_notes_url?: string;
  plugin_current?: string;
  plugin_latest?: string | null;
  plugin_update?: boolean;
  plugin_url?: string;
  plugin_hash?: string;
  plugin_notes_url?: string;
};

export const checkUpdates = callable<[force: boolean], UpdateInfo>("check_updates");
export const listOutdatedGames = callable<
  [],
  Result & { games: { appid: string; name: string; version: string }[]; active_version?: string | null }
>("list_outdated_games");
export const updateAllGames = callable<[], Result & { updated?: string[]; skipped?: string[] }>("update_all_games");
