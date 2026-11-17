import { useEffect, useState } from "react";
import { formatDate, formatSize } from "../format";
import type { DocumentItem, Folder } from "../types";
import { Icon } from "./Icon";

const STATUS_LABELS: Record<DocumentItem["status"], string> = {
  ready: "Hazır",
  failed: "İşlenemedi",
  pending: "Sırada",
  processing: "İşleniyor",
};

type FolderMenu = { documentId: string; top?: number; bottom?: number; right: number };

type Props = {
  hidden: boolean;
  documents: DocumentItem[];
  folders: Folder[];
  selectedIds: ReadonlySet<string>;
  uploading: boolean;
  retryingDocumentId: string | null;
  onToggleSelect: (document: DocumentItem) => void;
  onRetry: (document: DocumentItem) => void;
  onDelete: (document: DocumentItem) => void;
  onMove: (documentId: string, folderId: string | null) => void;
  onDeleteFolder: (folder: Folder) => void;
  /** null: create from the panel; a document id: create and move that document into it. */
  onCreateFolder: (documentId: string | null) => void;
  onUpload: () => void;
};

export function DocumentLibrary(props: Props) {
  const { documents, folders, selectedIds, retryingDocumentId } = props;
  const [collapsedFolders, setCollapsedFolders] = useState<ReadonlySet<string>>(() => new Set());
  const [folderMenu, setFolderMenu] = useState<FolderMenu | null>(null);

  useEffect(() => {
    if (!folderMenu) return;
    const close = (event: Event) => {
      if (event instanceof MouseEvent && (event.target as Element).closest(".folder-menu, .folder-button")) return;
      setFolderMenu(null);
    };
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") setFolderMenu(null); };
    window.addEventListener("mousedown", close);
    window.addEventListener("resize", close);
    window.addEventListener("scroll", close, true);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("resize", close);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("keydown", onKey);
    };
  }, [folderMenu]);

  function openFolderMenu(documentId: string, button: HTMLElement) {
    if (folderMenu?.documentId === documentId) { setFolderMenu(null); return; }
    const rect = button.getBoundingClientRect();
    const right = window.innerWidth - rect.right;
    // Open upwards near the bottom of the screen so the menu is not cut off.
    setFolderMenu(rect.bottom > window.innerHeight - 260
      ? { documentId, bottom: window.innerHeight - rect.top + 6, right }
      : { documentId, top: rect.bottom + 6, right });
  }

  function toggleFolder(folderId: string) {
    setCollapsedFolders(current => {
      const next = new Set(current);
      if (!next.delete(folderId)) next.add(folderId);
      return next;
    });
  }

  const menuDocument = folderMenu ? documents.find(item => item.id === folderMenu.documentId) : undefined;

  const renderDocument = (document: DocumentItem) => {
    const ready = document.status === "ready";
    const selected = ready && selectedIds.has(document.id);
    const busy = document.status === "pending" || document.status === "processing";
    return <li className={`document${selected ? " selected" : ""}`} key={document.id}>
      {ready
        ? <button type="button" className="file-icon file-select" aria-pressed={selected} title={selected ? "Sorulardan çıkar" : "Soruları bu dokümanla sınırla"} aria-label={`${document.original_filename}: ${selected ? "sorulardan çıkar" : "soruları bu dokümanla sınırla"}`} onClick={() => props.onToggleSelect(document)}>
          <Icon name={selected ? "check" : "file"} />
        </button>
        : <span className="file-icon" aria-hidden="true"><Icon name="file" /></span>}
      <div>
        <span className="document-name" title={document.original_filename}>{document.original_filename}</span>
        <div className="document-meta">
          <span className={`status ${document.status}`}>{STATUS_LABELS[document.status]}</span>
          <span>{formatSize(document.size_bytes)}</span>
          <span>{formatDate(document.created_at)}</span>
        </div>
        {document.status === "failed" && document.error_message && <p className="document-error">{document.error_message}</p>}
        {document.status === "failed" && <button className="retry-button" disabled={retryingDocumentId !== null} onClick={() => props.onRetry(document)}><Icon name="retry" />{retryingDocumentId === document.id ? "Başlatılıyor…" : "Yeniden dene"}</button>}
      </div>
      <div className="document-actions">
        <button type="button" className={`folder-button${folderMenu?.documentId === document.id ? " open" : ""}`} aria-haspopup="menu" aria-expanded={folderMenu?.documentId === document.id} aria-label="Klasöre taşı" title="Klasöre taşı" onClick={event => openFolderMenu(document.id, event.currentTarget)}><Icon name="folder" /></button>
        <button type="button" className="folder-button document-delete" aria-label={`${document.original_filename} dokümanını sil`} title={busy ? "İşlem bitince silinebilir" : "Sil"} disabled={busy} onClick={() => props.onDelete(document)}><Icon name="trash" /></button>
      </div>
    </li>;
  };

  return <>
    <aside id="document-sidebar" className="library" hidden={props.hidden}>
      <div className="library-head"><h2>Dokümanlar</h2><span className="count">{documents.length}</span></div>
      <button className="button soft library-folder" onClick={() => props.onCreateFolder(null)}><Icon name="folder" />Klasör oluştur</button>
      {documents.length || folders.length ? <div className="document-list">
        {folders.map(folder => {
          const open = !collapsedFolders.has(folder.id);
          const folderDocuments = documents.filter(item => item.folder_id === folder.id);
          return <section className="folder-group" key={folder.id}>
            <div className="folder-row">
              <button type="button" className="folder-toggle" aria-expanded={open} onClick={() => toggleFolder(folder.id)}>
                <Icon name="folder" /><span className="folder-name" title={folder.name}>{folder.name}</span>
                <span className="folder-count">{folderDocuments.length}</span>
                <span className={`folder-chevron${open ? " open" : ""}`}><Icon name="chevron" /></span>
              </button>
              <button type="button" className="folder-delete" aria-label={`${folder.name} klasörünü sil`} title="Klasörü sil" onClick={() => props.onDeleteFolder(folder)}><Icon name="close" /></button>
            </div>
            {open && (folderDocuments.length
              ? <ul className="folder-documents">{folderDocuments.map(renderDocument)}</ul>
              : <p className="folder-empty">Bu klasör boş.</p>)}
          </section>;
        })}
        {documents.some(item => !item.folder_id) && <ul className="folder-documents loose">{documents.filter(item => !item.folder_id).map(renderDocument)}</ul>}
      </div> : <div className="library-empty"><p>Henüz doküman yok.</p><p>PDF’leri buraya sürükleyin ya da aşağıdan ekleyin.</p></div>}
      <button className="button soft library-upload" onClick={props.onUpload} disabled={props.uploading}><Icon name="plus" />Doküman ekle</button>
    </aside>
    {folderMenu && menuDocument && <div className="folder-menu" role="menu" style={{ top: folderMenu.top, bottom: folderMenu.bottom, right: folderMenu.right }}>
      {folders.map(folder => <button key={folder.id} type="button" role="menuitem" onClick={() => { setFolderMenu(null); props.onMove(menuDocument.id, menuDocument.folder_id === folder.id ? null : folder.id); }}>
        <Icon name="folder" /><span>{folder.name}</span>{menuDocument.folder_id === folder.id && <span className="folder-menu-check"><Icon name="check" /></span>}
      </button>)}
      {folders.length > 0 && <hr />}
      <button type="button" role="menuitem" className="folder-menu-create" onClick={() => { setFolderMenu(null); props.onCreateFolder(menuDocument.id); }}><Icon name="plus" /><span>Yeni klasör oluştur</span></button>
    </div>}
  </>;
}
