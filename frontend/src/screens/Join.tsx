import {
  useRef,
  useState,
  type ClipboardEvent,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import { ChunkyButton, Header, PageShell, Sticker } from "../components/ui";
import { getClientId, saveSession } from "../session";
import askForCameraPermission from "../hooks/useCameraPermission";

const LEN = 4;
const NAME_MAX = 32;
const clean = (s: string) => s.toUpperCase().replace(/[^A-Z]/g, "");

export function Join() {
  const navigate = useNavigate();
  const [q] = useSearchParams();
  const initial = clean(q.get("code") ?? "").slice(0, LEN);
  const [cells, setCells] = useState(() =>
    Array.from({ length: LEN }, (_, i) => initial[i] ?? ""),
  );
  const [tag, setTag] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const refs = useRef<(HTMLInputElement | null)[]>([]);

  const code = cells.join("");
  const complete = code.length === LEN && !!tag.trim();

  const fill = (from: number, letters: string) => {
    const next = [...cells];
    for (let i = 0; i < letters.length && from + i < LEN; i++)
      next[from + i] = letters[i];
    setCells(next);
    refs.current[Math.min(from + letters.length, LEN - 1)]?.focus();
  };

  const onChange = (i: number, raw: string) => {
    const letters = clean(raw);
    if (!letters) {
      setCells((c) => c.map((v, j) => (j === i ? "" : v)));
      return;
    }
    // Typing into a filled box: keep the newest letter.
    fill(i, letters.length > 1 && cells[i] ? letters.slice(-1) : letters);
  };

  const onKeyDown = (i: number, e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace" && !cells[i] && i > 0) {
      e.preventDefault();
      setCells((c) => c.map((v, j) => (j === i - 1 ? "" : v)));
      refs.current[i - 1]?.focus();
    } else if (e.key === "ArrowLeft" && i > 0) refs.current[i - 1]?.focus();
    else if (e.key === "ArrowRight" && i < LEN - 1)
      refs.current[i + 1]?.focus();
  };

  const onPaste = (i: number, e: ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    fill(i, clean(e.clipboardData.getData("text")));
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const name = tag.trim();
    if (!complete || busy) return;
    setBusy(true);
    setError(null);
    try {
      // The join code is enough: the server resolves it to a room and mints this player's seat.
      const granted = await askForCameraPermission();
      if (granted) {
        const sess = await api.joinRoom(code, name, getClientId());
        saveSession(sess, name);
        navigate(`/lobby/${sess.join_code.toUpperCase()}`);
      } else {
        setError("You need to enable your webcam to play");
      }
      setBusy(false);
    } catch (err) {
      // 404 no such room, 409 game already started, 409 room full -- all worth showing verbatim.
      setError(
        err instanceof Error ? err.message : "Could not join that lobby",
      );
      setBusy(false);
    }
  };

  return (
    <PageShell bg="cyan" maxWidth={1100} gap={0} className="page--fit">
      <Header back="← back to safety" />

      <div className="join__main">
        <main className="card join__card">
          <Sticker>enter the code, bestie</Sticker>
          <h1>Join a lobby</h1>
          <p className="join__lede">
            4 letters. Your host has it. If they gatekept it, that's a them
            problem.
          </p>

          <form
            className="join__form"
            onSubmit={(e) => {
              void onSubmit(e);
            }}
          >
            <fieldset className="join__cells">
              <legend>Lobby code</legend>
              {cells.map((v, i) => (
                <span key={i}>
                  <label className="sr-only" htmlFor={`c${i + 1}`}>
                    Letter {i + 1}
                  </label>
                  <input
                    ref={(el) => {
                      refs.current[i] = el;
                    }}
                    id={`c${i + 1}`}
                    className={`cell ${v ? "cell--filled" : ""}`}
                    value={v}
                    maxLength={2}
                    autoComplete="off"
                    autoCapitalize="characters"
                    spellCheck={false}
                    inputMode="text"
                    onChange={(e) => onChange(i, e.target.value)}
                    onKeyDown={(e) => onKeyDown(i, e)}
                    onPaste={(e) => onPaste(i, e)}
                    onFocus={(e) => e.target.select()}
                  />
                </span>
              ))}
            </fieldset>

            <div className="join__tag">
              <label htmlFor="nick">Your gamer tag</label>
              <input
                id="nick"
                value={tag}
                placeholder="sigma_sam"
                maxLength={NAME_MAX}
                autoComplete="nickname"
                onChange={(e) => setTag(e.target.value)}
              />
            </div>

            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}

            <ChunkyButton
              type="submit"
              disabled={!complete || busy}
              className="join__go"
            >
              {busy ? "squeezing in…" : "Let me in →"}
            </ChunkyButton>
          </form>

          <p className="join__note">
            Heads up: we'll ask for your webcam. Your face is the controller.
          </p>
        </main>

        <div className="join__stickers">
          <Sticker
            bg="var(--white)"
            tilt="2deg"
            style={{ padding: "6px 12px", fontWeight: 600, fontSize: 15 }}
          >
            wrong code? skill issue
          </Sticker>
          <Sticker
            tilt="-2deg"
            style={{ padding: "6px 12px", fontWeight: 600, fontSize: 15 }}
          >
            lobby full? 12 is the limit
          </Sticker>
        </div>
      </div>
    </PageShell>
  );
}
