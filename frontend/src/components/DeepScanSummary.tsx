import { ChunkyButton, Modal, Pill } from "./ui";
import type { Round } from "../types";

/** One played round, as this player experienced it. */
interface ScanRound {
  number: number;
  prompt: string;
  target: string;
  /** What the processor read off this player's last frame; null when nothing was scored. */
  read: { label: string; confidence: number } | null;
  correct: boolean;
  points: number;
}

function scanRounds(rounds: Round[], playerId: string | undefined): ScanRound[] {
  return rounds.map((r) => {
    const sub = playerId ? r.submissions[playerId] : undefined;
    const result = sub?.status === "done" ? sub.result : null;
    return {
      number: r.number,
      prompt: r.prompt,
      target: r.target,
      read: result && { label: result.label, confidence: result.confidence },
      correct: sub?.correct === true,
      points: (playerId && r.points_awarded[playerId]) || 0,
    };
  });
}

function vibeCheck(rounds: ScanRound[]): string {
  const nailed = rounds.filter((r) => r.correct).length;
  const missed = rounds.find((r) => r.read && !r.correct);
  if (rounds.length === 0) return "No rounds, no damage. Suspicious.";
  if (nailed === rounds.length) return `${nailed} for ${nailed}. Every face landed. Uncle Damage is proud.`;
  if (nailed === 0) return `0 for ${rounds.length}. Your face said nothing the prompts asked for.`;
  const miss = missed ? ` "${missed.target}" came out ${missed.read!.label}.` : "";
  return `${nailed} of ${rounds.length} faces nailed.${miss} Uncle Damage saw everything.`;
}

/** End-of-game deep scan: every round actually played (`state.history`), in order. */
export function DeepScanSummary({
  open,
  onClose,
  rounds: history,
  playerId,
}: {
  open: boolean;
  onClose: () => void;
  rounds: Round[];
  playerId: string | undefined;
}) {
  const rounds = scanRounds(history, playerId);
  const reads = rounds.flatMap((r) => (r.read ? [r.read] : []));
  const confidence = reads.length
    ? Math.round((reads.reduce((sum, r) => sum + r.confidence, 0) / reads.length) * 100)
    : null;

  return (
    <Modal open={open} onClose={onClose} labelledBy="deepscan" className="deepscan">
      <div className="deepscan__head">
        {/* first focusable element, so the dialog opens scrolled to the top rather than on the button */}
        <h2 id="deepscan" tabIndex={-1}>
          Deep scan <small>(all {rounds.length} rounds of your soul)</small>
        </h2>
        {confidence !== null && (
          <Pill bg="var(--lime)" style={{ padding: "6px 14px" }}>
            read confidence {confidence}%
          </Pill>
        )}
      </div>

      <ol className="scan-rounds">
        {rounds.map((r) => (
          <li key={r.number} className="scan-round">
            <span className="scan-round__num">R{r.number}</span>
            <span className="scan-round__prompt">{r.prompt}</span>
            <span className="scan__sub">
              wanted {r.target} ·{" "}
              {r.read
                ? `read ${r.read.label} (${Math.round(r.read.confidence * 100)}%) ${r.correct ? "✓" : "✗"}`
                : "no face caught"}
            </span>
            <span className="scan-round__aura">+{r.points}</span>
          </li>
        ))}
      </ol>

      <div className="vibe">
        <span className="vibe__tag">AI vibe check</span>
        <span className="vibe__quote">"{vibeCheck(rounds)}"</span>
      </div>

      <div className="modal__actions">
        <ChunkyButton color="lime" onClick={onClose}>
          See who won
        </ChunkyButton>
      </div>
    </Modal>
  );
}
