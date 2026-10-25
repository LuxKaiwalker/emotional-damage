import { useState, type ReactNode } from "react";

/**
 * A home-screen face that pops up a reaction GIF while you point at it.
 *
 * Mouse: open on hover. Touch and keyboard: open on tap or focus, close on blur or Escape.
 * The <img> mounts on every open, so the GIF plays from the top each time and nothing is
 * downloaded until someone actually asks for it.
 */
export function FacePeek({
  gif,
  label,
  side,
  children,
}: {
  gif: string;
  label: string;
  /** Which column the face sits in: the popup opens toward the middle of the page. */
  side: "left" | "right";
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);

  return (
    <span
      className={`peek peek--${side}`}
      tabIndex={0}
      aria-label={`${label} reaction GIF`}
      aria-expanded={open}
      onPointerEnter={(e) => e.pointerType === "mouse" && setOpen(true)}
      onPointerLeave={(e) => e.pointerType === "mouse" && setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      onClick={() => setOpen(true)}
      onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
    >
      {children}
      {open && (
        <span className="peek__pop" role="tooltip">
          <img src={gif} alt="" className="peek__gif" />
          <span className="peek__label">{label}</span>
        </span>
      )}
    </span>
  );
}
