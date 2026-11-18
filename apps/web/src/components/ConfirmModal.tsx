import { type ReactNode, useEffect } from "react";

export function ConfirmModal({ title, message, confirmLabel = "Sil", danger = true, children, onConfirm, onClose }: {
  title: string; message: string; confirmLabel?: string; danger?: boolean; children?: ReactNode; onConfirm?: () => void; onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="modal" role="alertdialog" aria-modal="true" aria-labelledby="confirm-modal-title" aria-describedby="confirm-modal-text">
      <h2 id="confirm-modal-title">{title}</h2>
      <p id="confirm-modal-text" className="modal-text">{message}</p>
      {children}
      <div className="modal-actions">
        {/* Focus the safe choice for destructive actions, the confirm button otherwise. */}
        {/* Without onConfirm this is a plain notice popup with a single "Tamam" button. */}
        {onConfirm ? <>
          <button type="button" className="button soft" autoFocus={danger} onClick={onClose}>Vazgeç</button>
          <button type="button" className={`button primary${danger ? " modal-danger" : ""}`} autoFocus={!danger} onClick={onConfirm}>{confirmLabel}</button>
        </> : <button type="button" className="button primary" autoFocus onClick={onClose}>Tamam</button>}
      </div>
    </div>
  </div>;
}
