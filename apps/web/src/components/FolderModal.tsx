import { FormEvent, useEffect, useState } from "react";

export function FolderModal({ onClose, onCreate }: { onClose: () => void; onCreate: (name: string) => Promise<void> }) {
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  async function submit(event: FormEvent) {
    event.preventDefault();
    const value = name.trim();
    if (!value || saving) return;
    if (value.includes("@")) { setError("Klasör adı @ içeremez."); return; }
    setSaving(true); setError("");
    try { await onCreate(value); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Klasör oluşturulamadı."); setSaving(false); }
  }
  return <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <form className="modal" role="dialog" aria-modal="true" aria-labelledby="folder-modal-title" onSubmit={submit}>
      <h2 id="folder-modal-title">Yeni klasör</h2>
      <input autoFocus value={name} maxLength={50} onChange={event => setName(event.target.value)} placeholder="Klasör adı" aria-label="Klasör adı" />
      {error && <p className="modal-error" role="alert">{error}</p>}
      <div className="modal-actions">
        <button type="button" className="button soft" onClick={onClose}>Vazgeç</button>
        <button className="button primary" disabled={!name.trim() || saving}>{saving ? "Oluşturuluyor…" : "Oluştur"}</button>
      </div>
    </form>
  </div>;
}
