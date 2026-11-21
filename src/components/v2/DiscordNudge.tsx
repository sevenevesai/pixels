import { useCallback, useEffect, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { openUrl } from '@tauri-apps/plugin-opener';

export const DISCORD_APP_URL = 'https://seveneves.ai/discord/?from=pixels-app';
const DISCORD_NUDGE_URL = 'https://seveneves.ai/discord/?from=pixels-nudge';
const LAUNCH_COUNT_KEY = 'launch_count';
const SEEN_KEY = 'discord_nudge_seen';
const NUDGE_DELAY_MS = 3000;
const NUDGE_VISIBLE_MS = 12000;

export function openDiscord(url: string) {
  // Failing to open a browser must not surface an error in the editor.
  openUrl(url).catch(err => console.warn('Could not open Discord link:', err));
}

interface NudgeInputs {
  launchCount: number;
  seen: boolean;
  firstRun: boolean;
  busy: boolean;
  /** A save or bulk run finished successfully during this launch. */
  actionDone: boolean;
}

// The whole eligibility rule: never on the first launch, never twice, never while busy;
// from the 3rd launch, or earlier (launch 2) right after the first successful save or bulk run.
export function shouldShowNudge({ launchCount, seen, firstRun, busy, actionDone }: NudgeInputs): boolean {
  if (seen || firstRun || busy) return false;
  return launchCount >= 3 || actionDone;
}

interface LaunchState { launchCount: number; seen: boolean }

// Module-level so React StrictMode's double mount counts one launch.
let launchState: Promise<LaunchState | null> | null = null;

function readLaunchState(): Promise<LaunchState | null> {
  launchState ??= (async () => {
    try {
      const seen = await invoke<string | null>('get_app_setting', { key: SEEN_KEY });
      const stored = await invoke<string | null>('get_app_setting', { key: LAUNCH_COUNT_KEY });
      const previous = Number.parseInt(stored ?? '0', 10);
      const launchCount = (Number.isFinite(previous) && previous >= 0 ? previous : 0) + 1;
      await invoke<void>('set_app_setting', { key: LAUNCH_COUNT_KEY, value: String(launchCount) });
      return { launchCount, seen: seen === '1' };
    } catch {
      // Fail closed: if settings are unavailable the nudge is skipped without an error.
      return null;
    }
  })();
  return launchState;
}

export function useDiscordNudge(busy: boolean, actionDone: boolean) {
  const [launch, setLaunch] = useState<LaunchState | null>(null);
  const [ready, setReady] = useState(false);
  const [visible, setVisible] = useState(false);
  const [decided, setDecided] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void readLaunchState().then(state => {
      if (cancelled) return;
      setLaunch(state);
      // Let the app settle before the first evaluation.
      setTimeout(() => !cancelled && setReady(true), NUDGE_DELAY_MS);
    });
    return () => { cancelled = true; };
  }, []);

  const eligible = ready && !decided && launch !== null && shouldShowNudge({
    launchCount: launch.launchCount,
    seen: launch.seen,
    firstRun: launch.launchCount === 1,
    busy,
    actionDone,
  });

  useEffect(() => {
    if (!eligible) return;
    setDecided(true);
    // Seen is persisted before the card appears, so quitting while it is visible still counts.
    invoke<void>('set_app_setting', { key: SEEN_KEY, value: '1' })
      .then(() => setVisible(true))
      .catch(() => { /* fail closed: cannot record "seen", so never show */ });
  }, [eligible]);

  useEffect(() => {
    if (!visible) return;
    const timer = setTimeout(() => setVisible(false), NUDGE_VISIBLE_MS);
    return () => clearTimeout(timer);
  }, [visible]);

  const dismiss = useCallback(() => setVisible(false), []);
  return { visible, dismiss };
}

export function DiscordNudge({ busy, actionDone }: { busy: boolean; actionDone: boolean }) {
  const { visible, dismiss } = useDiscordNudge(busy, actionDone);
  if (!visible) return null;
  return (
    <div className="discord-nudge" role="status">
      <span>Found a bug or want a feature? Tell me on Discord.</span>
      <button
        className="discord-nudge-join"
        onClick={() => { openDiscord(DISCORD_NUDGE_URL); dismiss(); }}
      >
        Join
      </button>
      <button className="discord-nudge-close" aria-label="Close" onClick={dismiss}>×</button>
    </div>
  );
}
