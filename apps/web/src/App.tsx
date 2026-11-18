import { DragEvent, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api } from "./api";
import { formatSize } from "./format";
import { AssistantMessage } from "./components/AssistantMessage";
import { AuthScreen } from "./components/AuthScreen";
import { ConversationSidebar } from "./components/ConversationSidebar";
import { DocumentLibrary } from "./components/DocumentLibrary";
import { FolderModal } from "./components/FolderModal";
import { ConfirmModal } from "./components/ConfirmModal";
import { Icon } from "./components/Icon";
import { type AuthMode, LandingScreen } from "./components/LandingScreen";
import { ScopeBar } from "./components/ScopeBar";
import type { AuthSession, Conversation, ConversationDetail, DocumentItem, Feedback, Folder, Message, Source } from "./types";

const SESSION_KEY = "atlas-session";

function readSession(): AuthSession | null {
  try {
    const value = localStorage.getItem(SESSION_KEY);
    if (!value) return null;
    const session = JSON.parse(value) as AuthSession;
    return new Date(session.expires_at) > new Date() ? session : null;
  } catch { return null; }
}

const SUGGESTIONS = [
  { title: "Genel bir özet çıkar", hint: "Dokümanlardaki ana fikirleri kısaca topla", question: "Dokümanlardaki en önemli noktaları özetle." },
  { title: "Önemli kavramları bul", hint: "Terimleri ve tanımlarını listele", question: "Bu dokümanlarda geçen önemli kavramlar ve tanımları neler?" },
];

const isPdf = (file: File) => file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
const hasFiles = (event: DragEvent) => event.dataTransfer.types.includes("Files");
const isAbort = (caught: unknown) => caught instanceof DOMException && caught.name === "AbortError";

function App() {
  const [session, setSession] = useState<AuthSession | null>(readSession);
  const [started, setStarted] = useState(() => readSession() !== null);
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [sidebarOpen, setSidebarOpen] = useState(() => window.innerWidth > 720);
  const [libraryOpen, setLibraryOpen] = useState(() => window.innerWidth > 1050);
  const [organizationId, setOrganizationId] = useState("");
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [folders, setFolders] = useState<Folder[]>([]);
  // undefined = closed; null = opened from the panel; string = opened for that document, which then moves into the new folder.
  const [folderModalFor, setFolderModalFor] = useState<string | null | undefined>(undefined);
  // Scope of the new, not yet saved conversation; a saved one keeps its own on the server.
  const [draftScope, setDraftScope] = useState<string[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [active, setActive] = useState<ConversationDetail | null>(null);
  const [question, setQuestion] = useState("");
  const [pendingDelete, setPendingDelete] = useState<Conversation | null>(null);
  const [pendingFolderDelete, setPendingFolderDelete] = useState<Folder | null>(null);
  const [pendingDocumentDelete, setPendingDocumentDelete] = useState<DocumentItem | null>(null);
  const [asking, setAsking] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<{ done: number; total: number } | null>(null);
  const [dragging, setDragging] = useState(false);
  const [pendingUpload, setPendingUpload] = useState<File[] | null>(null);
  const [retryingDocumentId, setRetryingDocumentId] = useState<string | null>(null);
  const [pendingMessage, setPendingMessage] = useState<{ conversationId: string | null; message: Message } | null>(null);
  // null = no answer in flight; "" = waiting for the first token.
  const [streamingText, setStreamingText] = useState<string | null>(null);
  const [error, setError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const activeConversationId = useRef<string | null>(null);
  const conversationEnd = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const dragDepth = useRef(0);
  const uploadingRef = useRef(false);

  const logout = useCallback(() => {
    abortRef.current?.abort();
    // Best effort: revoke the token on the server so a copied token stops working too.
    const stored = readSession();
    if (stored) api.logout(stored.access_token).catch(() => undefined);
    localStorage.removeItem(SESSION_KEY); setSession(null); setStarted(true);
  }, []);
  const handleError = useCallback((caught: unknown) => {
    if (caught instanceof ApiError && caught.status === 401) { logout(); return; }
    setError(caught instanceof Error ? caught.message : "Beklenmeyen bir hata oluştu.");
  }, [logout]);

  const refreshDocuments = useCallback(async () => {
    if (!session || !organizationId) return;
    try { setDocuments((await api.documents(organizationId, session.access_token)).items); }
    catch (caught) { handleError(caught); }
  }, [session, organizationId, handleError]);

  const refreshFolders = useCallback(async () => {
    if (!session || !organizationId) return;
    try { setFolders((await api.folders(organizationId, session.access_token)).items); }
    catch (caught) { handleError(caught); }
  }, [session, organizationId, handleError]);

  const refreshConversations = useCallback(async () => {
    if (!session || !organizationId) return;
    try { setConversations((await api.conversations(organizationId, session.access_token)).items); }
    catch (caught) { handleError(caught); }
  }, [session, organizationId, handleError]);

  const refresh = useCallback(async () => {
    await Promise.all([refreshDocuments(), refreshConversations(), refreshFolders()]);
  }, [refreshDocuments, refreshConversations, refreshFolders]);

  useEffect(() => { if (session && !organizationId) setOrganizationId(session.organization_id ?? session.organization_ids[0] ?? ""); }, [session, organizationId]);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (!documents.some(document => document.status === "pending" || document.status === "processing")) return;
    const timer = window.setTimeout(() => { void refreshDocuments(); }, 2000);
    return () => window.clearTimeout(timer);
  }, [documents, refreshDocuments]);
  useEffect(() => () => abortRef.current?.abort(), []);

  const currentScope = active ? active.document_ids ?? [] : draftScope;
  const currentScopeSet = useMemo(() => new Set(currentScope), [currentScope]);

  const showsPending = pendingMessage !== null && pendingMessage.conversationId === (active?.id ?? null);
  const visibleMessages = useMemo(() => {
    const messages = active?.messages ?? [];
    if (!showsPending || !pendingMessage) return messages;
    const draft: Message[] = streamingText ? [{ ...pendingMessage.message, id: "draft-answer", role: "assistant", content: streamingText, sources: [] }] : [];
    return [...messages, pendingMessage.message, ...draft];
  }, [active, pendingMessage, showsPending, streamingText]);

  useEffect(() => {
    conversationEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [visibleMessages.length, asking]);
  // Follow the streaming answer only while the reader is at the bottom; never yank them back up-scroll.
  useEffect(() => {
    const content = contentRef.current;
    if (!streamingText || !content) return;
    if (content.scrollHeight - content.scrollTop - content.clientHeight < 160) conversationEnd.current?.scrollIntoView({ block: "end" });
  }, [streamingText]);

  function authenticated(value: AuthSession) { localStorage.setItem(SESSION_KEY, JSON.stringify(value)); setSession(value); }

  async function openConversation(item: Conversation) {
    if (!session) return;
    activeConversationId.current = item.id;
    try {
      const detail = await api.conversation(organizationId, item.id, session.access_token);
      if (activeConversationId.current === item.id) setActive(detail);
      setError("");
    }
    catch (caught) { handleError(caught); }
  }

  function startNewConversation(scope: string[] = []) {
    activeConversationId.current = null;
    setActive(null);
    setDraftScope(scope);
    closeOverlays();
  }

  async function ask(event: FormEvent) {
    event.preventDefault(); if (!session || !question.trim() || asking) return;
    const content = question.trim();
    const targetConversationId = active?.id ?? null;
    const optimistic: Message = {
      id: crypto.randomUUID(),
      conversation_id: targetConversationId ?? "",
      role: "user",
      content,
      sequence: (active?.messages.at(-1)?.sequence ?? 0) + 1,
      created_at: new Date().toISOString(),
      sources: [],
    };
    const controller = new AbortController();
    abortRef.current = controller;
    setQuestion(""); setAsking(true); setError(""); setStreamingText("");
    setPendingMessage({ conversationId: targetConversationId, message: optimistic });
    try {
      const result = await api.askStream(
        organizationId,
        // A saved conversation's scope is read on the server; a new one sends its draft, which gets saved.
        { question: content, conversation_id: targetConversationId, document_ids: targetConversationId || !draftScope.length ? null : draftScope },
        session.access_token,
        text => setStreamingText(current => (current ?? "") + text),
        controller.signal,
      );
      const detail = await api.conversation(organizationId, result.conversation_id, session.access_token);
      if (activeConversationId.current === targetConversationId) {
        activeConversationId.current = result.conversation_id;
        setActive(detail);
      }
      await refreshConversations();
    } catch (caught) {
      // Give the question back to edit or resend, unless something new was typed meanwhile.
      if (activeConversationId.current === targetConversationId) setQuestion(current => current || content);
      if (!isAbort(caught)) handleError(caught);
    }
    finally { abortRef.current = null; setPendingMessage(null); setStreamingText(null); setAsking(false); }
  }

  // Stopping drops the connection; the server cancels generation and saves nothing.
  const stop = () => abortRef.current?.abort();

  async function uploadFiles(files: File[]) {
    if (!session || !files.length) return;
    if (uploadingRef.current) { setError("Önceki yükleme sürüyor; bitince tekrar deneyin."); return; }
    const pdfs = files.filter(isPdf);
    const problems = files.length > pdfs.length ? [`${files.length - pdfs.length} dosya PDF olmadığı için atlandı.`] : [];
    uploadingRef.current = true; setError("");
    // One at a time: the server indexes each upload in the background and shares one model.
    try {
      for (const [index, file] of pdfs.entries()) {
        setUploadProgress({ done: index, total: pdfs.length });
        try {
          const document = await api.upload(organizationId, file, session.access_token);
          setDocuments(current => [document, ...current.filter(item => item.id !== document.id)]);
        } catch (caught) {
          if (caught instanceof ApiError && caught.status === 401) { logout(); return; }
          problems.push(`${file.name}: ${caught instanceof Error ? caught.message : "yüklenemedi"}`);
        }
      }
    } finally {
      uploadingRef.current = false;
      setUploadProgress(null);
      if (fileInput.current) fileInput.current.value = "";
    }
    if (problems.length) setError(problems.join(" "));
  }

  function onDragEnter(event: DragEvent) {
    if (!hasFiles(event)) return;
    event.preventDefault(); dragDepth.current += 1; setDragging(true);
  }
  function onDragOver(event: DragEvent) {
    if (!hasFiles(event)) return;
    event.preventDefault(); event.dataTransfer.dropEffect = "copy";
  }
  // Enter/leave fire for every child element; count them so the overlay does not flicker.
  function onDragLeave(event: DragEvent) {
    if (!hasFiles(event)) return;
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setDragging(false);
  }
  // Dropped files wait for confirmation: a drop is easy to make by accident, a picker choice is not.
  function onDrop(event: DragEvent) {
    if (!hasFiles(event)) return;
    event.preventDefault(); dragDepth.current = 0; setDragging(false);
    const files = [...event.dataTransfer.files];
    if (uploadingRef.current) { setError("Önceki yükleme sürüyor; bitince tekrar deneyin."); return; }
    if (!files.some(isPdf)) { setError("Yalnızca PDF dosyaları eklenebilir."); return; }
    setPendingUpload(files);
  }

  function confirmPendingUpload() {
    const files = pendingUpload;
    setPendingUpload(null);
    if (files) void uploadFiles(files);
  }

  async function addFolder(name: string) {
    if (!session) return;
    try {
      const folder = await api.createFolder(organizationId, name, session.access_token);
      setFolders(current => [...current, folder].sort((a, b) => a.name.localeCompare(b.name, "tr")));
      const documentId = folderModalFor;
      setFolderModalFor(undefined);
      if (documentId) await moveDocument(documentId, folder.id);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) { logout(); return; }
      throw caught; // shown inside the modal
    }
  }
  async function removeFolder(folder: Folder) {
    if (!session) return; setError("");
    try {
      await api.deleteFolder(organizationId, folder.id, session.access_token);
      setFolders(current => current.filter(item => item.id !== folder.id));
      setDocuments(current => current.map(item => item.folder_id === folder.id ? { ...item, folder_id: null } : item));
    } catch (caught) { handleError(caught); }
  }
  async function moveDocument(documentId: string, folderId: string | null) {
    if (!session) return; setError("");
    try {
      const document = await api.moveDocument(organizationId, documentId, folderId, session.access_token);
      setDocuments(current => current.map(item => item.id === document.id ? document : item));
    } catch (caught) { handleError(caught); }
  }

  async function retryDocument(document: DocumentItem) {
    if (!session || retryingDocumentId) return;
    setRetryingDocumentId(document.id); setError("");
    try {
      const updated = await api.retryDocument(organizationId, document.id, session.access_token);
      setDocuments(current => current.map(item => item.id === updated.id ? updated : item));
    } catch (caught) { handleError(caught); }
    finally { setRetryingDocumentId(null); }
  }

  async function removeDocument(document: DocumentItem) {
    if (!session) return;
    setError("");
    try {
      await api.deleteDocument(organizationId, document.id, session.access_token);
      setDocuments(current => current.filter(item => item.id !== document.id));
      // The server already dropped it from every conversation's scope; mirror that locally.
      setDraftScope(current => current.filter(id => id !== document.id));
      setActive(current => current && { ...current, document_ids: (current.document_ids ?? []).filter(id => id !== document.id) });
      setConversations(current => current.map(item => ({ ...item, document_ids: (item.document_ids ?? []).filter(id => id !== document.id) })));
      // Sources from this document are gone server-side; reload so the open answer stops showing them.
      if (active?.messages.some(message => message.sources.some(source => source.document_id === document.id))) {
        const conversationId = active.id;
        const detail = await api.conversation(organizationId, conversationId, session.access_token);
        if (activeConversationId.current === conversationId) setActive(detail);
      }
    } catch (caught) { handleError(caught); }
  }

  async function changeScope(documentIds: string[]) {
    if (!session) return;
    if (!active) { setDraftScope(documentIds); return; }
    const conversationId = active.id;
    const previous = active.document_ids ?? [];
    const apply = (ids: string[]) => {
      setActive(current => current?.id === conversationId ? { ...current, document_ids: ids } : current);
      setConversations(current => current.map(item => item.id === conversationId ? { ...item, document_ids: ids } : item));
    };
    apply(documentIds);
    try { apply(await api.setConversationDocuments(organizationId, conversationId, documentIds, session.access_token)); }
    catch (caught) { apply(previous); handleError(caught); }
  }

  function toggleScope(document: DocumentItem) {
    void changeScope(currentScopeSet.has(document.id) ? currentScope.filter(id => id !== document.id) : [...currentScope, document.id]);
  }

  async function renameConversation(conversation: Conversation, title: string) {
    if (!session) return; setError("");
    try {
      const updated = await api.renameConversation(organizationId, conversation.id, title, session.access_token);
      setConversations(current => current.map(item => item.id === updated.id ? updated : item));
      setActive(current => current?.id === updated.id ? { ...current, title: updated.title } : current);
    } catch (caught) { handleError(caught); }
  }

  async function removeConversation(conversation: Conversation) {
    if (!session) return;
    setPendingDelete(null);
    setError("");
    try {
      await api.deleteConversation(organizationId, conversation.id, session.access_token);
      setConversations(current => current.filter(item => item.id !== conversation.id));
      if (activeConversationId.current === conversation.id) { activeConversationId.current = null; setActive(null); }
    } catch (caught) { handleError(caught); }
  }

  async function sendFeedback(message: Message, value: Feedback) {
    if (!session) return;
    const previous = message.feedback ?? null;
    const apply = (feedback: Feedback) => setActive(current => current && {
      ...current,
      messages: current.messages.map(item => item.id === message.id ? { ...item, feedback } : item),
    });
    apply(value);
    try { await api.setFeedback(organizationId, message.conversation_id, message.id, value, session.access_token); }
    catch (caught) { apply(previous); handleError(caught); }
  }

  async function openSourcePdf(source: Source) {
    if (!session) return;
    // Opened synchronously inside the click so popup blockers allow it; filled once the file arrives.
    const viewer = window.open("", "_blank");
    if (!viewer) { setError("Açılır pencere engellendi. Bu site için açılır pencerelere izin verin."); return; }
    viewer.document.title = source.filename;
    try {
      const blob = await api.documentFile(organizationId, source.document_id, session.access_token);
      const url = URL.createObjectURL(blob);
      viewer.location.href = `${url}#page=${source.page_number}`;
      // The viewer keeps its own copy once loaded; free ours after a generous delay.
      window.setTimeout(() => URL.revokeObjectURL(url), 10 * 60 * 1000);
    } catch (caught) { viewer.close(); handleError(caught); }
  }

  const closeFolderModal = useCallback(() => setFolderModalFor(undefined), []);

  if (!started) return <LandingScreen onStart={mode => { setAuthMode(mode ?? "login"); setStarted(true); }} hasSession={session !== null} />;
  if (!session) return <AuthScreen onAuthenticated={authenticated} initialMode={authMode} />;
  if (!organizationId) return <main className="empty-page"><h2>Bu hesaba bağlı bir organizasyon bulunamadı.</h2><button className="button soft" onClick={logout}>Çıkış yap</button></main>;

  const hasReadyDocument = documents.some(document => document.status === "ready");
  const uploading = uploadProgress !== null;
  function closeOverlays() {
    if (window.innerWidth <= 720) setSidebarOpen(false);
    if (window.innerWidth <= 1050) setLibraryOpen(false);
  }

  return <main
    className={`app${sidebarOpen ? "" : " no-sidebar"}${libraryOpen ? "" : " no-library"}`}
    onDragEnter={onDragEnter} onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}
  >
    <ConversationSidebar
      hidden={!sidebarOpen}
      conversations={conversations}
      activeId={active?.id ?? null}
      busyId={asking ? pendingMessage?.conversationId ?? null : null}
      email={session.user.email}
      onHome={() => setStarted(false)}
      onNew={() => startNewConversation()}
      onOpen={item => { closeOverlays(); void openConversation(item); }}
      onRename={renameConversation}
      onDelete={setPendingDelete}
      onLogout={logout}
    />
    <section className="workspace">
      <header className="workspace-header">
        <button className="icon-button" type="button" aria-controls="conversation-sidebar" aria-expanded={sidebarOpen} aria-label={sidebarOpen ? "Konuşma panelini kapat" : "Konuşma panelini aç"} title={sidebarOpen ? "Konuşma panelini kapat" : "Konuşma panelini aç"} onClick={() => setSidebarOpen(value => !value)}><Icon name="panelLeft" /></button>
        <h1 className="workspace-title">{active?.title ?? "Yeni konuşma"}</h1>
        <div className="header-actions">
          <button className="button soft" onClick={() => fileInput.current?.click()} disabled={uploading} aria-label="PDF yükle"><Icon name="upload" /><span>{uploadProgress ? `Yükleniyor ${uploadProgress.done + 1}/${uploadProgress.total}` : "PDF yükle"}</span></button>
          <button className="icon-button" type="button" aria-controls="document-sidebar" aria-expanded={libraryOpen} aria-label={libraryOpen ? "Doküman panelini kapat" : "Doküman panelini aç"} title={libraryOpen ? "Doküman panelini kapat" : "Doküman panelini aç"} onClick={() => setLibraryOpen(value => !value)}><Icon name="panelRight" /></button>
          <input ref={fileInput} hidden type="file" multiple accept="application/pdf,.pdf" onChange={event => void uploadFiles([...(event.target.files ?? [])])} />
        </div>
      </header>
      <ScopeBar documents={documents} scopeIds={currentScope} onChange={ids => void changeScope(ids)} />
      <div className="content" ref={contentRef}>
        {!visibleMessages.length ? <section className="welcome">
          <h2>Ne öğrenmek istersiniz?</h2>
          <p>{hasReadyDocument
            ? "Dokümanlarınızla ilgili bir soru yazın. Her cevabın altında kullanılan sayfaları görürsünüz."
            : "Başlamak için PDF'lerinizi buraya sürükleyin ya da yükleyin. Doküman işlendiğinde sorularınızı yanıtlamaya hazır olur."}</p>
          <div className="suggestions">{SUGGESTIONS.map(item => <button key={item.title} className="suggestion" onClick={() => setQuestion(item.question)}><b>{item.title}</b><span>{item.hint}</span></button>)}</div>
        </section> : <div className="message-list">
          {visibleMessages.map(message => <article key={message.id} className={`message ${message.role}`} aria-label={message.role === "user" ? "Sorunuz" : "Asistanın cevabı"} aria-busy={message.id === "draft-answer" || undefined}>
            {message.role === "user"
              ? <div className="bubble">{message.content}</div>
              : message.id === "draft-answer"
                ? <AssistantMessage message={message} streaming onOpenPdf={openSourcePdf} />
                : <AssistantMessage message={message} onOpenPdf={openSourcePdf} onFeedback={sendFeedback} />}
          </article>)}
          {asking && showsPending && !streamingText && <div className="thinking" role="status"><span className="dots" aria-hidden="true"><i /><i /><i /></span>Kaynaklar taranıyor</div>}
          <div ref={conversationEnd} />
        </div>}
      </div>
      <footer className="composer-area">
        <form className="composer" onSubmit={ask}>
          <textarea value={question} onChange={event => setQuestion(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} placeholder="Dokümanlarınız hakkında bir soru sorun…" aria-label="Sorunuz" rows={1} />
          {asking
            ? <button type="button" className="send-button stop" onClick={stop} aria-label="Cevabı durdur" title="Durdur"><Icon name="stop" /></button>
            : <button className="send-button" disabled={!question.trim()} aria-label="Gönder" title="Gönder"><Icon name="send" /></button>}
        </form>
        <p className="composer-note">Yanıtlar yalnızca yüklediğiniz dokümanlara dayanır.</p>
      </footer>
    </section>
    <DocumentLibrary
      hidden={!libraryOpen}
      documents={documents}
      folders={folders}
      selectedIds={currentScopeSet}
      uploading={uploading}
      retryingDocumentId={retryingDocumentId}
      onToggleSelect={toggleScope}
      onChatWithDocument={document => startNewConversation([document.id])}
      onChatWithFolder={folder => startNewConversation(documents.filter(item => item.folder_id === folder.id && item.status === "ready").map(item => item.id))}
      onRetry={document => void retryDocument(document)}
      onDelete={setPendingDocumentDelete}
      onMove={(documentId, folderId) => void moveDocument(documentId, folderId)}
      onDeleteFolder={setPendingFolderDelete}
      onCreateFolder={setFolderModalFor}
      onUpload={() => fileInput.current?.click()}
    />
    {pendingDelete && <ConfirmModal
      title="Konuşma silinsin mi?"
      message={`"${pendingDelete.title ?? "Başlıksız konuşma"}" konuşması ve tüm mesajları kalıcı olarak silinecek. Bu işlem geri alınamaz.`}
      onConfirm={() => void removeConversation(pendingDelete)}
      onClose={() => setPendingDelete(null)}
    />}
    {pendingFolderDelete && <ConfirmModal
      title="Klasör silinsin mi?"
      message={`"${pendingFolderDelete.name}" klasörü silinecek. Dokümanlar silinmez.`}
      onConfirm={() => { const folder = pendingFolderDelete; setPendingFolderDelete(null); void removeFolder(folder); }}
      onClose={() => setPendingFolderDelete(null)}
    />}
    {pendingDocumentDelete && <ConfirmModal
      title="Doküman silinsin mi?"
      message={`"${pendingDocumentDelete.original_filename}" kalıcı olarak silinecek. Bu dokümana dayanan eski cevapların kaynakları da kaldırılır. Bu işlem geri alınamaz.`}
      onConfirm={() => { const document = pendingDocumentDelete; setPendingDocumentDelete(null); void removeDocument(document); }}
      onClose={() => setPendingDocumentDelete(null)}
    />}
    {error && <ConfirmModal title="Uyarı" message={error} danger={false} onClose={() => setError("")} />}
    {pendingUpload && (() => {
      const pdfs = pendingUpload.filter(isPdf);
      const skipped = pendingUpload.length - pdfs.length;
      return <ConfirmModal
        title={pdfs.length === 1 ? "Doküman eklensin mi?" : `${pdfs.length} doküman eklensin mi?`}
        message={skipped ? `PDF olmayan ${skipped} dosya eklenmeyecek.` : "Eklenen dokümanlar işlendikten sonra sorularda kullanılır."}
        confirmLabel={pdfs.length === 1 ? "Dokümanı ekle" : "Dokümanları ekle"}
        danger={false}
        onConfirm={confirmPendingUpload}
        onClose={() => setPendingUpload(null)}
      >
        <ul className="pending-files">{pdfs.map((file, index) => <li key={`${index}-${file.name}`}>
          <Icon name="file" /><span title={file.name}>{file.name}</span><small>{formatSize(file.size)}</small>
        </li>)}</ul>
      </ConfirmModal>;
    })()}
    {folderModalFor !== undefined &&<FolderModal onClose={closeFolderModal} onCreate={addFolder} />}
    {dragging && <div className="drop-overlay" aria-hidden="true"><div><Icon name="upload" /><b>PDF'leri bırakın</b><span>Birden fazla dosya seçebilirsiniz</span></div></div>}
    <button className="scrim" aria-label="Paneli kapat" tabIndex={-1} onClick={closeOverlays} />
  </main>;
}

export default App;
