import { useEffect, useRef, useState } from "react";
import type { DocumentItem } from "../types";
import { Icon } from "./Icon";

type Props = {
  documents: DocumentItem[];
  /** Documents the conversation is limited to; empty means all documents. */
  scopeIds: string[];
  onChange: (documentIds: string[]) => void;
};

export function ScopeBar({ documents, scopeIds, onChange }: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const byId = new Map(documents.map(document => [document.id, document]));
  // A scoped document deleted elsewhere is no longer in the list; the server drops it too.
  const scoped = scopeIds.map(id => byId.get(id)).filter((document): document is DocumentItem => document !== undefined);
  const addable = documents.filter(document => document.status === "ready" && !scopeIds.includes(document.id));

  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: Event) => {
      if (event instanceof MouseEvent && root.current?.contains(event.target as Node)) return;
      setMenuOpen(false);
    };
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") setMenuOpen(false); };
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("mousedown", close); window.removeEventListener("keydown", onKey); };
  }, [menuOpen]);

  return <div className="scope-bar" ref={root} aria-label="Konuşmanın dokümanları">
    {scoped.length === 0 && <span className="scope-all">Tüm dokümanlarda aranıyor</span>}
    {scoped.map(document => <span key={document.id} className={`scope-doc${document.status === "ready" ? "" : " not-ready"}`} title={document.status === "ready" ? document.original_filename : `${document.original_filename} (henüz hazır değil)`}>
      <Icon name="file" /><span className="scope-doc-name">{document.original_filename}</span>
      <button type="button" aria-label={`${document.original_filename} dokümanını konuşmadan çıkar`} title="Konuşmadan çıkar" onClick={() => onChange(scopeIds.filter(id => id !== document.id))}><Icon name="close" /></button>
    </span>)}
    <div className="scope-add-wrap">
      <button type="button" className="scope-add" aria-haspopup="menu" aria-expanded={menuOpen} disabled={!addable.length} title={addable.length ? undefined : "Eklenecek hazır doküman yok"} onClick={() => setMenuOpen(open => !open)}>
        <Icon name="plus" />{scoped.length ? "Doküman" : "Dokümanla sınırla"}
      </button>
      {menuOpen && <div className="scope-menu" role="menu">
        {addable.map(document => <button key={document.id} type="button" role="menuitem" onClick={() => { setMenuOpen(false); onChange([...scopeIds, document.id]); }}>
          <Icon name="file" /><span>{document.original_filename}</span>
        </button>)}
      </div>}
    </div>
  </div>;
}
