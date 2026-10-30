import { useEffect, useRef, useSyncExternalStore } from "react";

import { getBand } from "./engine";
import { music } from "./music";
import type { TrackName } from "./tracks";

/**
 * Put `track` on, and keep its tempo and intensity in step with the screen.
 *
 * The player outlives screens, so the next screen's track simply takes over -- there is
 * no stop on unmount, which would leave a gap of silence between every route change.
 */
export function useMusic(track: TrackName | null, params: { intensity?: number; tempo?: number } = {}) {
  const { intensity = 0.5, tempo = 1 } = params;

  useEffect(() => {
    music.play(track);
  }, [track]);

  useEffect(() => {
    music.params = { intensity, tempo };
  }, [intensity, tempo]);
}

/**
 * Run `effect` when `value` changes, with the value it changed from -- but not for the
 * value a screen mounts with. A player count that is already 4 when the lobby opens is
 * not four people joining.
 */
export function useOnChange<T>(value: T, effect: (next: T, prev: T) => void) {
  const prev = useRef(value);
  const latest = useRef(effect);
  useEffect(() => {
    latest.current = effect;
  });

  useEffect(() => {
    if (Object.is(prev.current, value)) return;
    const before = prev.current;
    prev.current = value;
    latest.current(value, before);
  }, [value]);
}

/** The mute switch, shared by every component that shows it. */
export function useSoundMuted(): [muted: boolean, setMuted: (muted: boolean) => void] {
  const band = getBand();
  const muted = useSyncExternalStore(
    (onChange) => band.subscribe(onChange),
    () => band.muted,
  );
  return [muted, (next) => band.setMuted(next)];
}
