import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";

/**
 * Play a round's narration once, when the server says it is ready.
 *
 * `audio_id` arrives late -- generation takes seconds and the round has already started --
 * so this watches for it rather than expecting it up front. Each id is played at most
 * once, because a re-render or a fresh snapshot must not restart the line.
 *
 * Autoplay with sound needs a prior user gesture. Creating a lobby or joining one is a
 * click, which normally satisfies it, but a blocked `play()` is reported rather than
 * thrown: the line is also on screen as text.
 */
export function useNarration(audioId: string | null | undefined): { blocked: boolean } {
  const [blocked, setBlocked] = useState(false);
  const playedRef = useRef<string | null>(null);

  useEffect(() => {
    if (!audioId || playedRef.current === audioId) return;
    playedRef.current = audioId;

    const audio = new Audio(api.voiceUrl(audioId));
    audio.play().then(
      () => setBlocked(false),
      () => setBlocked(true), // autoplay policy, or the audio expired (404)
    );

    return () => {
      audio.pause();
      audio.src = "";
    };
  }, [audioId]);

  return { blocked };
}
