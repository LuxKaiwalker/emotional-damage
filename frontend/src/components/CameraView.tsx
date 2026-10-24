import type { Camera } from "../hooks/useCamera";
import type { UploaderStatus } from "../hooks/useFrameUploader";

export function CameraView({
  camera,
  uploader,
  capturing,
}: {
  camera: Camera;
  uploader: UploaderStatus;
  capturing: boolean;
}) {
  return (
    <div className="panel camera">
      <div className="camera-frame">
        {/* muted + playsInline are required for autoplay to work in most browsers. */}
        <video ref={camera.videoRef} autoPlay muted playsInline />
        {capturing && <span className="rec">● capturing</span>}
      </div>

      {camera.error ? (
        <div className="error">
          <p>{camera.error}</p>
          <button onClick={camera.start}>Retry camera</button>
        </div>
      ) : (
        <p className="muted small">
          {camera.ready ? "camera live" : "waiting for camera permission…"} · sent {uploader.sent} ·
          skipped {uploader.skipped} · failed {uploader.failed}
        </p>
      )}
    </div>
  );
}
