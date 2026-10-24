import { Eye } from "./art";
import { ChunkyButton, MeterBar, Modal, Pill, Waveform } from "./ui";
import { gameScan as ds } from "../mock/data";

/** End-of-game deep scan: what Presage read off your face across every round. */
export function DeepScanSummary({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Modal open={open} onClose={onClose} labelledBy="deepscan" className="deepscan">
      <div className="deepscan__head">
        {/* first focusable element, so the dialog opens scrolled to the top rather than on the button */}
        <h2 id="deepscan" tabIndex={-1}>
          Deep scan <small>(all {ds.rounds.length} rounds of your soul)</small>
        </h2>
        <Pill bg="var(--lime)" style={{ padding: "6px 14px" }}>
          signal confidence {ds.signalConfidence}% · {ds.stability}
        </Pill>
      </div>

      <ol className="scan-rounds">
        {ds.rounds.map((r) => (
          <li key={r.round} className="scan-round">
            <span className="scan-round__num">R{r.round}</span>
            <span className="scan-round__prompt">{r.prompt}</span>
            <span className="scan__sub">
              {r.peakPulse} bpm peak · HRV {r.hrv} ms · {r.topExpression}
            </span>
            <span className="scan-round__aura">+{r.aura}</span>
          </li>
        ))}
      </ol>

      <div className="scan-grid">
        <div className="scan" style={{ background: "var(--tint-pink)" }}>
          <div className="scan__head">
            <h3>Heart goes brr</h3>
            <span>pulse pleth</span>
          </div>
          <Waveform points={ds.pulseWave} label="Pulse waveform, five sharp beats" />
          <div className="scan__row">
            <span className="scan__big">avg HRV {ds.hrv} ms</span>
            <span className="scan__sub">
              {ds.hrvVsBaseline < 0 ? "↓" : "↑"} {Math.abs(ds.hrvVsBaseline)}% vs your baseline = stressed fr
            </span>
          </div>
        </div>

        <div className="scan" style={{ background: "var(--tint-cyan)" }}>
          <div className="scan__head">
            <h3>Panic breathing</h3>
            <span>upper vs lower</span>
          </div>
          <div className="overlay" role="img" aria-label="Breathing waveforms: chest line large and fast, belly line small">
            <Waveform points={ds.breathingUpper} smooth decorative />
            <Waveform points={ds.breathingLower} smooth dashed decorative />
          </div>
          <div style={{ display: "flex", gap: 14, flexWrap: "wrap", fontWeight: 600, fontSize: 14 }}>
            <span>— chest (upper)</span>
            <span>- - belly (lower)</span>
          </div>
          <div className="scan__big">chest-heavy: shallow &amp; fast. certified panic.</div>
        </div>

        <div className="scan" style={{ background: "var(--tint-yellow)" }}>
          <div className="scan__head">
            <h3>Pressure check</h3>
            <span>relative BP waveform</span>
          </div>
          <Waveform points={ds.bpWave} smooth label="Relative blood pressure waveform trending upward" />
          <div className="scan__row">
            <span className="scan__big">trend {{ up: "↑ climbing", down: "↓ dropping", flat: "→ flat" }[ds.bpTrend]}</span>
            <span className="scan__sub">relative, not a medical reading</span>
          </div>
        </div>

        <div className="scan" style={{ background: "var(--tint-lime)" }}>
          <div className="scan__head">
            <h3>Face classifier</h3>
            <span>expression</span>
          </div>
          {ds.expressions.map((e) => (
            <div key={e.label} className="classifier-row">
              <span>{e.label}</span>
              <MeterBar value={e.pct} label={e.label} color={e.color} />
              <span>{e.pct}%</span>
            </div>
          ))}
        </div>

        <div className="scan">
          <div className="scan__head">
            <h3>Eye snitch</h3>
            <span>iris + blinks</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
            <Eye gaze={ds.gazeVector} label={`Eye looking ${ds.gaze}`} />
            <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
              <span className="scan__big">gaze: {ds.gaze}</span>
              <span className="scan__sub">
                looked away {ds.lookAways}× (sus) · {ds.blinks} blinks · {ds.squints} squint
                {ds.squints === 1 ? "" : "s"}
              </span>
            </div>
          </div>
          <div className="penalty">
            eye contact penalty: {ds.eyePenalty < 0 ? "−" : "+"}
            {Math.abs(ds.eyePenalty)} aura
          </div>
        </div>

        <div className="scan">
          <div className="scan__head">
            <h3>Commitment</h3>
            <span>face points + talking</span>
          </div>
          <div className="grid2" style={{ gap: 10 }}>
            {[
              ["mouth stretch", `${ds.face.mouthStretch}%`],
              ["brow crunch", `${ds.face.browCrunch}%`],
              ["held the face", `${ds.face.heldSeconds}s`],
              ["screamed", ds.face.screamed ? "yes" : "no"],
            ].map(([k, v]) => (
              <div key={k}>
                <div className="scan__sub">{k}</div>
                <div className="commit-val">{v}</div>
              </div>
            ))}
          </div>
          <div className="scan__sub">
            lighting {ds.face.lighting} · face {ds.face.inFrame}% in frame · stability good
          </div>
        </div>
      </div>

      <div className="vibe">
        <span className="vibe__tag">AI vibe check</span>
        <span className="vibe__quote">"{ds.vibeCheck}"</span>
      </div>

      <div className="modal__actions">
        <ChunkyButton color="lime" onClick={onClose}>
          See who won
        </ChunkyButton>
      </div>
    </Modal>
  );
}
