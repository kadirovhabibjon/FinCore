import { useEffect, useState, type ReactNode } from "react";

const DISARM_AFTER_MS = 5_000;

/** A button for something that can't be taken back with one more click
 * (rejecting a payment, withdrawing an announcement): the first press
 * only arms it, showing what the second press will do; it disarms by
 * itself if left alone or when the pointer goes elsewhere. */
export function ConfirmButton({
  children,
  confirm,
  onConfirm,
  className = "button button-small",
  disabled = false,
}: {
  children: ReactNode;
  /** What the armed button says, e.g. "Confirm reject". */
  confirm: string;
  onConfirm: () => void;
  className?: string;
  disabled?: boolean;
}) {
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    if (!armed) return;
    const timer = setTimeout(() => setArmed(false), DISARM_AFTER_MS);
    return () => clearTimeout(timer);
  }, [armed]);

  return (
    <button
      type="button"
      className={`${className}${armed ? " button-armed" : ""}`}
      disabled={disabled}
      onBlur={() => setArmed(false)}
      onClick={() => {
        if (!armed) {
          setArmed(true);
          return;
        }
        setArmed(false);
        onConfirm();
      }}
    >
      {armed ? confirm : children}
    </button>
  );
}
