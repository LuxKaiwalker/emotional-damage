import { useEffect, useRef, type CSSProperties, type ReactNode } from "react";
import { Link } from "react-router-dom";

type Tilt = { tilt?: string };

/** Sets the `--tilt` var read by `.tilt`, so mobile can cap rotations in one place. */
const tiltStyle = (tilt: string | undefined, style?: CSSProperties) =>
  ({ ...style, "--tilt": tilt ?? "0deg" }) as CSSProperties;

export function PageShell({
  bg,
  maxWidth = 1180,
  gap = 36,
  className = "",
  innerClassName = "",
  padding,
  children,
}: {
  bg: "yellow" | "pink" | "cyan" | "lime";
  maxWidth?: number;
  gap?: number;
  className?: string;
  innerClassName?: string;
  padding?: string;
  children: ReactNode;
}) {
  return (
    <div className={`page dots dots--${bg} ${className}`} style={padding ? { padding } : undefined}>
      <div className={`page__inner ${innerClassName}`} style={{ maxWidth, gap }}>
        {children}
      </div>
    </div>
  );
}

export function Header({ back, to = "/" }: { back: string; to?: string }) {
  return (
    <header className="header">
      <Link to={to} className="pill-link">
        {back}
      </Link>
      <span className="wordmark">EMOTIONAL DAMAGE</span>
    </header>
  );
}

export function ChunkyCard({
  tilt,
  className = "",
  style,
  as: Tag = "div",
  children,
  ...rest
}: Tilt & {
  className?: string;
  style?: CSSProperties;
  as?: "div" | "section" | "aside" | "main";
  children: ReactNode;
  "aria-labelledby"?: string;
  id?: string;
}) {
  return (
    <Tag className={`card tilt ${className}`} style={tiltStyle(tilt, style)} {...rest}>
      {children}
    </Tag>
  );
}

type ButtonColor = "yellow" | "lime" | "white";

export function ChunkyButton({
  to,
  onClick,
  color = "yellow",
  size,
  disabled,
  type = "button",
  className = "",
  children,
}: {
  to?: string;
  onClick?: () => void;
  color?: ButtonColor;
  size?: "lg" | "plain";
  disabled?: boolean;
  type?: "button" | "submit";
  className?: string;
  children: ReactNode;
}) {
  const cls = `btn chunky-btn chunky-btn--${color} ${size ? `chunky-btn--${size}` : ""} ${className}`;
  if (to && !disabled) {
    return (
      <Link to={to} className={cls}>
        {children}
      </Link>
    );
  }
  return (
    <button type={type} className={cls} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
}

export function Sticker({
  bg = "var(--pink)",
  tilt = "-3deg",
  shadow,
  style,
  children,
}: Tilt & { bg?: string; shadow?: boolean; style?: CSSProperties; children: ReactNode }) {
  return (
    <span
      className="sticker tilt"
      style={tiltStyle(tilt, { background: bg, boxShadow: shadow ? "var(--shadow-sm)" : undefined, ...style })}
    >
      {children}
    </span>
  );
}

export function Avatar({
  initial,
  color,
  size = 50,
  dashed,
}: {
  initial: string;
  color?: string;
  size?: 44 | 50 | 58 | 170;
  dashed?: boolean;
}) {
  const font = { 44: 20, 50: 24, 58: 28, 170: 90 }[size];
  return (
    <span
      className="avatar"
      aria-hidden="true"
      style={{
        width: size,
        height: size,
        fontSize: font,
        background: color,
        borderWidth: size === 58 ? 4 : undefined,
        borderStyle: dashed ? "dashed" : undefined,
      }}
    >
      {initial}
    </span>
  );
}

export function Pill({
  bg = "var(--white)",
  thin,
  dark,
  style,
  children,
}: {
  bg?: string;
  thin?: boolean;
  dark?: boolean;
  style?: CSSProperties;
  children: ReactNode;
}) {
  return (
    <span
      className={`pill ${thin ? "pill--thin" : ""} ${dark ? "pill--dark" : ""}`}
      style={{ background: dark ? undefined : bg, ...style }}
    >
      {children}
    </span>
  );
}

export function MetricTile({
  label,
  value,
  unit,
  caption,
  bg,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  caption: string;
  bg: string;
}) {
  return (
    <div className="metric" style={{ background: bg }}>
      <div className="metric__label">{label}</div>
      <div className="metric__value">
        {value}
        {unit && <span className="metric__unit"> {unit}</span>}
      </div>
      <div className="metric__caption">{caption}</div>
    </div>
  );
}

export function MeterBar({
  value,
  label,
  color,
  height = 18,
  divider,
}: {
  value: number;
  label: string;
  color: string;
  height?: number;
  divider?: boolean;
}) {
  return (
    <div
      className="meter"
      style={{ height }}
      role="meter"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
    >
      <div
        className="meter__fill"
        style={{ width: `${value}%`, background: color, borderRight: divider ? "var(--border-thin)" : undefined }}
      />
    </div>
  );
}

export function Countdown({ seconds }: { seconds: number }) {
  const done = seconds <= 0;
  return (
    <>
      <div
        className={`countdown ${done ? "countdown--done" : ""}`}
        role="timer"
        aria-label={done ? "Time's up" : `${seconds} second${seconds === 1 ? "" : "s"} left`}
      >
        <span className="countdown__num">{done ? "captured!" : seconds}</span>
        <span className="countdown__label">{done ? "nice." : "FACE NOW"}</span>
      </div>
      <span className="sr-only" aria-live="assertive">
        {seconds === 0 ? "FACE NOW" : ""}
      </span>
    </>
  );
}

/**
 * Chunky modal on a native <dialog>: focus trap, Esc to close and the backdrop come for free.
 * Clicking the backdrop also closes it.
 */
export function Modal({
  open,
  onClose,
  labelledBy,
  describedBy,
  className = "",
  children,
}: {
  open: boolean;
  onClose: () => void;
  labelledBy: string;
  describedBy?: string;
  className?: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className={`modal ${className}`}
      aria-labelledby={labelledBy}
      aria-describedby={describedBy}
      onClose={onClose}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      {children}
    </dialog>
  );
}
