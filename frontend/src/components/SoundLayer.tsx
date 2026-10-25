import { useEffect } from "react";

import { useSoundMuted } from "../audio/hooks";
import { sfx } from "../audio/sfx";

/**
 * App-wide audio chrome: the mute toggle, and a click sound for every button.
 *
 * Clicks are caught by one delegated listener rather than wired into each button, so
 * every current and future button sounds the same without remembering to opt in.
 */
export function SoundLayer() {
  const [muted, setMuted] = useSoundMuted();

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      const target = event.target as Element | null;
      const button = target?.closest("button, a.btn, [role=button]");
      if (!button || (button as HTMLButtonElement).disabled) return;
      if (button.closest("[data-sound-toggle]")) return;
      sfx.click();
    };
    // "M" toggles sound, unless the player is typing a name or a code.
    const onKey = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== "m" || event.metaKey || event.ctrlKey || event.altKey) return;
      const el = document.activeElement;
      if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) return;
      if (el instanceof HTMLElement && el.isContentEditable) return;
      setMuted(!muted);
    };
    document.addEventListener("click", onClick, true);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("click", onClick, true);
      window.removeEventListener("keydown", onKey);
    };
  }, [muted, setMuted]);

  return (
    <button
      type="button"
      className="sound-toggle"
      data-sound-toggle
      aria-pressed={!muted}
      aria-label={muted ? "Sound off. Turn sound on (M)" : "Sound on. Turn sound off (M)"}
      title={muted ? "Sound off (M)" : "Sound on (M)"}
      onClick={() => setMuted(!muted)}
    >
      <svg viewBox="0 0 16 16" width="22" height="22" aria-hidden="true" shapeRendering="crispEdges">
        {/* A chunky pixel speaker. */}
        <path d="M2 6h3v4H2zM5 5h1v6H5zM6 4h1v8H6zM7 3h1v10H7z" fill="currentColor" />
        {muted ? (
          <path className="sound-toggle__glyph" d="M10 6h1v1h-1zM11 7h1v1h-1zM12 8h1v1h-1zM13 9h1v1h-1zM13 6h1v1h-1zM12 7h1v1h-1zM11 8h1v1h-1zM10 9h1v1h-1z" fill="currentColor" />
        ) : (
          <path className="sound-toggle__glyph" d="M9 6h1v4H9zM11 4h1v1h-1zM12 5h1v6h-1zM11 11h1v1h-1z" fill="currentColor" />
        )}
      </svg>
    </button>
  );
}
