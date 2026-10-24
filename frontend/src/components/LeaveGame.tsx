import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { UncleDamage } from "./art";
import { ChunkyButton, Modal } from "./ui";

/**
 * "Leave game" pill plus an "are you sure" modal. Leaving only happens on an explicit yes;
 * Esc, the backdrop and "stay" all cancel. `onOpenChange` lets a screen pause its timers.
 */
export function LeaveGame({ onOpenChange }: { onOpenChange?: (open: boolean) => void }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    onOpenChange?.(open);
  }, [open, onOpenChange]);

  return (
    <>
      <button type="button" className="btn pill-link leave-btn" onClick={() => setOpen(true)}>
        ← leave game
      </button>
      <Modal open={open} onClose={() => setOpen(false)} labelledBy="leave-title" describedBy="leave-desc">
        <UncleDamage className="modal__face" />
        <h2 id="leave-title">Are you sure?</h2>
        <p id="leave-desc">You'll forfeit this game and all your aura. Uncle Damage will remember this.</p>
        <div className="modal__actions">
          <ChunkyButton color="lime" onClick={() => setOpen(false)}>
            Nah, I'm staying
          </ChunkyButton>
          <ChunkyButton color="white" onClick={() => navigate("/")}>
            Yes, rage quit
          </ChunkyButton>
        </div>
      </Modal>
    </>
  );
}
