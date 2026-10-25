import { useCallback } from "react";

/**
 * A preview of the game's camera, which `GameShell` keeps running between rounds.
 *
 * Shared by the round and blitz screens: `useSmartSpectra` owns the one `getUserMedia`
 * and hands out the raw stream, so a screen only has to point a <video> at it.
 */
export function Webcam({
  stream,
  ready,
  error,
}: {
  stream: MediaStream | null;
  ready: boolean;
  error: string | null;
}) {
  const attach = useCallback(
    (video: HTMLVideoElement | null) => {
      if (video && video.srcObject !== stream) video.srcObject = stream;
    },
    [stream],
  );

  return (
    <section className="webcam" aria-label="Your webcam">
      <video ref={attach} autoPlay muted playsInline hidden={!ready} />
      {error && (
        <p className="webcam__msg">
          <b>camera said no</b>
          {error}
        </p>
      )}
    </section>
  );
}
