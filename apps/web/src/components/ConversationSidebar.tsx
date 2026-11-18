import { useRef, useState } from "react";
import { formatDate } from "../format";
import type { Conversation } from "../types";
import { Icon } from "./Icon";

type Props = {
  hidden: boolean;
  conversations: Conversation[];
  activeId: string | null;
  /** A conversation whose answer is still streaming cannot be deleted mid-save. */
  busyId: string | null;
  email: string;
  onHome: () => void;
  onNew: () => void;
  onOpen: (conversation: Conversation) => void;
  onRename: (conversation: Conversation, title: string) => Promise<void>;
  onDelete: (conversation: Conversation) => void;
  onLogout: () => void;
};

export function ConversationSidebar(props: Props) {
  const { conversations, activeId, busyId } = props;
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  // Enter submits and unmounts the input, which can also fire blur: save only once.
  const editingRef = useRef<string | null>(null);

  function startEditing(conversation: Conversation) {
    editingRef.current = conversation.id;
    setEditingId(conversation.id);
    setDraft(conversation.title ?? "");
  }

  function cancel() {
    editingRef.current = null;
    setEditingId(null);
  }

  async function save(conversation: Conversation) {
    if (editingRef.current !== conversation.id) return;
    editingRef.current = null;
    const title = draft.trim().slice(0, 255);
    setEditingId(null);
    if (title && title !== conversation.title) await props.onRename(conversation, title);
  }

  return <aside id="conversation-sidebar" className="sidebar" hidden={props.hidden}>
    <button className="home-link" onClick={props.onHome}><Icon name="home" />Ana sayfa</button>
    <button className="button primary new-chat" onClick={props.onNew}><Icon name="plus" />Yeni konuşma</button>
    <h2 className="sidebar-heading">Konuşmalar</h2>
    <nav className="conversation-list" aria-label="Konuşmalar">
      {conversations.length ? conversations.map(item => {
        const active = activeId === item.id;
        if (editingId === item.id) {
          return <form key={item.id} className="conversation-item editing" onSubmit={event => { event.preventDefault(); void save(item); }}>
            <input
              className="conversation-rename"
              autoFocus
              value={draft}
              maxLength={255}
              aria-label="Konuşma adı"
              onChange={event => setDraft(event.target.value)}
              onBlur={() => void save(item)}
              onKeyDown={event => { if (event.key === "Escape") { event.preventDefault(); cancel(); } }}
            />
          </form>;
        }
        return <div key={item.id} className={`conversation-row${active ? " active" : ""}`}>
          <button className={`conversation-item${active ? " active" : ""}`} aria-current={active ? "page" : undefined} onClick={() => props.onOpen(item)}>
            <span className="conversation-title">
              {(item.document_ids?.length ?? 0) > 0 && <span className="conversation-scope" title={`${item.document_ids.length} dokümanla sınırlı`} aria-label={`${item.document_ids.length} dokümanla sınırlı`}><Icon name="file" /></span>}
              {item.title ?? "Başlıksız konuşma"}
            </span>
            <span className="conversation-date">{formatDate(item.updated_at)}</span>
          </button>
          <div className="conversation-actions">
            <button type="button" className="row-action" title="Yeniden adlandır" aria-label={`${item.title ?? "Konuşma"} adını değiştir`} onClick={() => startEditing(item)}><Icon name="pencil" /></button>
            <button type="button" className="row-action danger" title={busyId === item.id ? "Cevap tamamlanınca silinebilir" : "Sil"} aria-label={`${item.title ?? "Konuşma"} konuşmasını sil`} disabled={busyId === item.id} onClick={() => props.onDelete(item)}><Icon name="trash" /></button>
          </div>
        </div>;
      }) : <p className="sidebar-empty">Sorduğunuz sorular burada listelenir.</p>}
    </nav>
    <div className="account">
      <span className="avatar" aria-hidden="true">{props.email[0].toUpperCase()}</span>
      <span className="account-email" title={props.email}>{props.email}</span>
      <button className="icon-button" title="Çıkış yap" aria-label="Çıkış yap" onClick={props.onLogout}><Icon name="logout" /></button>
    </div>
  </aside>;
}
