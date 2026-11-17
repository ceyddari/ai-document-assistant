import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api } from "./api";
import type { AuthSession, Conversation, ConversationDetail, DocumentItem, Folder, Message, Source } from "./types";

const SESSION_KEY = "atlas-session";

function readSession(): AuthSession | null {
  try {
    const value = localStorage.getItem(SESSION_KEY);
    if (!value) return null;
    const session = JSON.parse(value) as AuthSession;
    return new Date(session.expires_at) > new Date() ? session : null;
  } catch { return null; }
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

const ICONS = {
  plus: "M12 5v14M5 12h14",
  upload: "M12 15V4m0 0L8 8m4-4 4 4M5 15v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3",
  send: "M12 19V5m0 0-6 6m6-6 6 6",
  panelLeft: "M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zM9.5 4v16",
  panelRight: "M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zM14.5 4v16",
  logout: "M14 12H4m0 0 3.5-3.5M4 12l3.5 3.5M12 4h6a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-6",
  file: "M7 3h7l5 5v12a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zM14 3v5h5M9.5 13h5M9.5 16.5h5",
  retry: "M20 11a8 8 0 0 0-14.3-4.9L4 8m0-4v4h4M4 13a8 8 0 0 0 14.3 4.9L20 16m0 4v-4h-4",
  close: "M6 6l12 12M18 6 6 18",
  chevron: "M9 6l6 6-6 6",
  folder: "M3.5 7a1.5 1.5 0 0 1 1.5-1.5h4l2 2h8a1.5 1.5 0 0 1 1.5 1.5v8.5a1.5 1.5 0 0 1-1.5 1.5H5a1.5 1.5 0 0 1-1.5-1.5z",
  check: "M5 12.5 10 17 19 7",
  home: "M4 11.5 12 5l8 6.5M6.5 10v9h11v-9M10 19v-5h4v5",
  arrowUpRight: "M7 7h10v10M7 17 17 7",
  arrowRight: "M5 12h14m0 0-6-6m6 6-6 6",
} as const;

function Icon({ name }: { name: keyof typeof ICONS }) {
  return <svg className="icon" viewBox="0 0 24 24" aria-hidden="true"><path d={ICONS[name]} /></svg>;
}

const SUGGESTIONS = [
  { title: "Genel bir özet çıkar", hint: "Dokümanlardaki ana fikirleri kısaca topla", question: "Dokümanlardaki en önemli noktaları özetle." },
  { title: "Süreçleri bul", hint: "Adımları ve sorumlulukları listele", question: "Bu dokümanlarda hangi süreçler anlatılıyor?" },
];

const STATUS_LABELS: Record<DocumentItem["status"], string> = {
  ready: "Hazır",
  failed: "İşlenemedi",
  pending: "Sırada",
  processing: "İşleniyor",
};

function formatSize(bytes: number) {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

// Spring-follows the cursor over the image's area (max 20px shift, ±5° tilt); off on touch and reduced motion.
function useLotusMotion() {
  const ref = useRef<HTMLImageElement>(null);
  useEffect(() => {
    const img = ref.current, area = img?.parentElement;
    if (!img || !area || !matchMedia("(hover: hover) and (pointer: fine)").matches || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const target = { x: 0, y: 0 }, pos = { x: 0, y: 0 }, vel = { x: 0, y: 0 };
    let frame = 0, last = 0;
    const step = (now: number) => {
      const dt = Math.min((now - last) / 1000, 1 / 30); last = now;
      for (const k of ["x", "y"] as const) { vel[k] += (70 * (target[k] - pos[k]) - 14 * vel[k]) * dt; pos[k] += vel[k] * dt; }
      img.style.transform = `perspective(900px) translate3d(${pos.x * 20}px, ${pos.y * 20}px, 0) rotateX(${-pos.y * 5}deg) rotateY(${pos.x * 5}deg)`;
      const settled = Math.abs(target.x - pos.x) + Math.abs(target.y - pos.y) + Math.abs(vel.x) + Math.abs(vel.y) < 0.001;
      frame = settled ? 0 : requestAnimationFrame(step);
    };
    const aim = (x: number, y: number) => {
      target.x = x; target.y = y;
      if (!frame) { last = performance.now(); frame = requestAnimationFrame(step); }
    };
    // The visual has pointer-events: none (it overlaps the copy), so track on window and test against its rect.
    const onMove = (e: PointerEvent) => {
      const r = area.getBoundingClientRect();
      const inside = e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
      aim(inside ? ((e.clientX - r.left) / r.width) * 2 - 1 : 0, inside ? ((e.clientY - r.top) / r.height) * 2 - 1 : 0);
    };
    const reset = () => aim(0, 0);
    window.addEventListener("pointermove", onMove, { passive: true });
    document.documentElement.addEventListener("mouseleave", reset);
    return () => {
      window.removeEventListener("pointermove", onMove);
      document.documentElement.removeEventListener("mouseleave", reset);
      cancelAnimationFrame(frame);
    };
  }, []);
  return ref;
}

function HoverButton({ text, onClick }: { text: string; onClick: () => void }) {
  return <button className="hover-button" onClick={onClick}>
    <span className="hover-button-label">{text}</span>
    <span className="hover-button-reveal" aria-hidden="true">{text}<Icon name="arrowRight" /></span>
    <span className="hover-button-dot" aria-hidden="true" />
  </button>;
}

type AuthMode = "login" | "register";

function LandingScreen({ onStart, hasSession }: { onStart: (mode?: AuthMode) => void; hasSession: boolean }) {
  const lotusRef = useLotusMotion();
  return <main className="landing-shell">
    <nav className="landing-nav">
      <span className="nav-note">AI DOCUMENT INTELLIGENCE</span>
      <div className="landing-actions">
        {hasSession
          ? <HoverButton text="Uygulamaya dön" onClick={() => onStart()} />
          : <><HoverButton text="Giriş yap" onClick={() => onStart("login")} /><HoverButton text="Kayıt ol" onClick={() => onStart("register")} /></>}
      </div>
    </nav>
    <div className="landing-glow glow-one" /><div className="landing-glow glow-two" />
    <section className="landing-copy">
      <p className="landing-kicker"><i /> Kurumsal bilginin yeni formu</p>
      <h1>Bilginiz.<br /><em>Canlı, bağlantılı</em><br />ve erişilebilir.</h1>
      <p>Dağınık dokümanlarınızı kaynaklarıyla konuşabilen güvenilir bir bilgi merkezine dönüştürün.</p>
      <button className="colorful-button" onClick={() => onStart()}>
        <span className="colorful-glow" aria-hidden="true" />
        <span className="colorful-content">{hasSession ? "Dokümanlara git" : "Başla"}<Icon name="arrowUpRight" /></span>
      </button>
    </section>
    <section className="landing-visual" aria-hidden="true">
      <div className="visual-orbit orbit-a" /><div className="visual-orbit orbit-b" />
      <img ref={lotusRef} src="/atlas-knowledge-core.png" alt="" />
    </section>
    <footer className="landing-footer"><span>DOCUMENTS</span><span>KNOWLEDGE</span><span>CONVERSATIONS</span></footer>
  </main>;
}

function AuthScreen({ onAuthenticated, initialMode }: { onAuthenticated: (session: AuthSession) => void; initialMode: AuthMode }) {
  const [mode, setMode] = useState<AuthMode>(initialMode);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setLoading(true); setError("");
    const data = new FormData(event.currentTarget);
    try {
      const session = mode === "login"
        ? await api.login(String(data.get("email")), String(data.get("password")))
        : await api.register({
          email: String(data.get("email")), password: String(data.get("password")),
          organization_name: String(data.get("organization_name")), organization_slug: String(data.get("organization_slug")),
        });
      onAuthenticated(session);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Bağlantı kurulamadı."); }
    finally { setLoading(false); }
  }

  return <main className="auth-shell">
    <section className="auth-story">
      <div className="story-copy">
        <p className="eyebrow">Kurumsal bilgi, tek bir yerde</p>
        <h1>Dokümanlarınız<br />cevaba dönüşsün.</h1>
        <p>Şirket bilginizi güvenle arayın, kaynaklarını görün ve her konuşmayı kaldığınız yerden sürdürün.</p>
      </div>
      <div className="quote-card"><span>“</span><p>Doğru cevap kadar, o cevabın nereden geldiğini bilmek de önemli.</p></div>
    </section>
    <section className="auth-panel">
      <div className="auth-card">
        <p className="eyebrow">{mode === "login" ? "Tekrar hoş geldiniz" : "Yeni çalışma alanı"}</p>
        <h2>{mode === "login" ? "Hesabınıza giriş yapın" : "Kullanmaya başlayın"}</h2>
        <p className="muted">{mode === "login" ? "Dokümanlarınıza ve konuşmalarınıza devam edin." : "Hesabınızla birlikte ilk organizasyonunuz oluşturulur."}</p>
        <form onSubmit={submit}>
          {mode === "register" && <div className="field-row">
            <label>Organizasyon adı<input name="organization_name" required placeholder="Acme Teknoloji" /></label>
            <label>Kısa adres<input name="organization_slug" required pattern="[a-z0-9]+(?:-[a-z0-9]+)*" placeholder="acme-teknoloji" /></label>
          </div>}
          <label>E-posta<input name="email" type="email" required placeholder="siz@sirket.com" autoComplete="email" /></label>
          <label>Parola<input name="password" type="password" required minLength={mode === "register" ? 6 : 1} placeholder="••••••••••••" autoComplete={mode === "login" ? "current-password" : "new-password"} /></label>
          {error && <div className="error-banner">{error}</div>}
          <button className="primary-button" disabled={loading}>{loading ? "Lütfen bekleyin…" : mode === "login" ? "Giriş yap" : "Çalışma alanı oluştur"}<span>→</span></button>
        </form>
        <button className="text-button" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}>
          {mode === "login" ? "Hesabınız yok mu? Kayıt olun" : "Zaten hesabınız var mı? Giriş yapın"}
        </button>
      </div>
    </section>
  </main>;
}

function SourceList({ sources }: { sources: Source[] }) {
  if (!sources.length) return null;
  return <div className="sources">
    <p className="sources-label">Kaynaklar</p>
    {sources.map((source, index) => <details className="source" key={source.chunk_id}>
      <summary>
        <span className="cite">{index + 1}</span>
        <span className="source-name" title={source.filename}>{source.filename}</span>
        <span className="source-page">s. {source.page_number}</span>
        <span className="source-score" title="Benzerlik">%{Math.round(source.similarity * 100)}</span>
      </summary>
      <blockquote>{source.content}</blockquote>
    </details>)}
  </div>;
}

function renderInlineFormatting(content: string): ReactNode[] {
  return content.split(/(\*\*[^*]+\*\*|\[Kaynak\s*\d+\])/g).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>;
    }
    const citation = /^\[Kaynak\s*(\d+)\]$/.exec(part);
    if (citation) return <span key={`${part}-${index}`} className="cite" title={`Kaynak ${citation[1]}`}>{citation[1]}</span>;
    return part;
  });
}

function MessageContent({ content }: { content: string }) {
  return <div className="message-content">{content.split("\n").map((line, index) => (
    <p key={`${index}-${line}`} className={/^\s*[-•*]\s/.test(line) ? "bullet-line" : undefined}>
      {renderInlineFormatting(line)}
    </p>
  ))}</div>;
}

function FolderModal({ onClose, onCreate }: { onClose: () => void; onCreate: (name: string) => Promise<void> }) {
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

function App() {
  const [session, setSession] = useState<AuthSession | null>(readSession);
  const [started, setStarted] = useState(() => readSession() !== null);
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [sidebarOpen, setSidebarOpen] = useState(() => window.innerWidth > 720);
  const [libraryOpen, setLibraryOpen] = useState(() => window.innerWidth > 1050);
  const [organizationId, setOrganizationId] = useState("");
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [collapsedFolders, setCollapsedFolders] = useState<Set<string>>(() => new Set());
  const [folderMenu, setFolderMenu] = useState<{ documentId: string; top?: number; bottom?: number; right: number } | null>(null);
  // undefined = closed; null = opened from the sidebar; string = opened from that document's menu, which then moves into the new folder.
  const [folderModalFor, setFolderModalFor] = useState<string | null | undefined>(undefined);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [active, setActive] = useState<ConversationDetail | null>(null);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [retryingDocumentId, setRetryingDocumentId] = useState<string | null>(null);
  const [pendingMessage, setPendingMessage] = useState<{
    conversationId: string | null;
    message: Message;
  } | null>(null);
  const [error, setError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const activeConversationId = useRef<string | null>(null);
  const conversationEnd = useRef<HTMLDivElement>(null);

  const logout = useCallback(() => { localStorage.removeItem(SESSION_KEY); setSession(null); setStarted(true); }, []);
  const handleError = useCallback((caught: unknown) => {
    if (caught instanceof ApiError && caught.status === 401) { logout(); return; }
    setError(caught instanceof Error ? caught.message : "Beklenmeyen bir hata oluştu.");
  }, [logout]);

  const refreshDocuments = useCallback(async () => {
    if (!session || !organizationId) return;
    try {
      const result = await api.documents(organizationId, session.access_token);
      setDocuments(result.items);
    } catch (caught) { handleError(caught); }
  }, [session, organizationId, handleError]);

  const refreshFolders = useCallback(async () => {
    if (!session || !organizationId) return;
    try { setFolders((await api.folders(organizationId, session.access_token)).items); }
    catch (caught) { handleError(caught); }
  }, [session, organizationId, handleError]);

  const refreshConversations = useCallback(async () => {
    if (!session || !organizationId) return;
    try {
      const result = await api.conversations(organizationId, session.access_token);
      setConversations(result.items);
    } catch (caught) { handleError(caught); }
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

  const visibleMessages = useMemo(() => {
    const messages = active?.messages ?? [];
    if (!pendingMessage || pendingMessage.conversationId !== (active?.id ?? null)) return messages;
    return [...messages, pendingMessage.message];
  }, [active, pendingMessage]);

  useEffect(() => {
    conversationEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [visibleMessages.length, asking]);

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
    setQuestion(""); setAsking(true); setError("");
    setPendingMessage({ conversationId: targetConversationId, message: optimistic });
    try {
      const result = await api.ask(organizationId, content, targetConversationId, session.access_token);
      const detail = await api.conversation(organizationId, result.conversation_id, session.access_token);
      if (activeConversationId.current === targetConversationId) {
        activeConversationId.current = result.conversation_id;
        setActive(detail);
      }
      await refreshConversations();
    } catch (caught) {
      if (activeConversationId.current === targetConversationId) setQuestion(content);
      handleError(caught);
    }
    finally { setPendingMessage(null); setAsking(false); }
  }
  async function upload(file?: File) {
    if (!file || !session) return; setUploading(true); setError("");
    try {
      const document = await api.upload(organizationId, file, session.access_token);
      setDocuments(current => [document, ...current.filter(item => item.id !== document.id)]);
    }
    catch (caught) { handleError(caught); }
    finally { setUploading(false); if (fileInput.current) fileInput.current.value = ""; }
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
  function openFolderMenu(documentId: string, button: HTMLElement) {
    if (folderMenu?.documentId === documentId) { setFolderMenu(null); return; }
    const rect = button.getBoundingClientRect();
    const right = window.innerWidth - rect.right;
    // Open upwards near the bottom of the screen so the menu is not cut off.
    setFolderMenu(rect.bottom > window.innerHeight - 260
      ? { documentId, bottom: window.innerHeight - rect.top + 6, right }
      : { documentId, top: rect.bottom + 6, right });
  }
  async function removeFolder(folder: Folder) {
    if (!session || !window.confirm(`"${folder.name}" klasörü silinsin mi? Dokümanlar silinmez.`)) return; setError("");
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
  function mentionFolder(folder: Folder) {
    setQuestion(current => `${current}${current && !current.endsWith(" ") ? " " : ""}@${folder.name} `);
  }

  async function retryDocument(documentId: string) {
    if (!session || retryingDocumentId) return;
    setRetryingDocumentId(documentId); setError("");
    try {
      const document = await api.retryDocument(
        organizationId,
        documentId,
        session.access_token,
      );
      setDocuments(current => current.map(item => item.id === document.id ? document : item));
    } catch (caught) { handleError(caught); }
    finally { setRetryingDocumentId(null); }
  }

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
  const closeFolderModal = useCallback(() => setFolderModalFor(undefined), []);
  const menuDocument = folderMenu ? documents.find(item => item.id === folderMenu.documentId) : undefined;

  if (!started) return <LandingScreen onStart={mode => { setAuthMode(mode ?? "login"); setStarted(true); }} hasSession={session !== null} />;
  if (!session) return <AuthScreen onAuthenticated={authenticated} initialMode={authMode} />;
  if (!organizationId) return <main className="empty-page"><h2>Bu hesaba bağlı bir organizasyon bulunamadı.</h2><button className="button soft" onClick={logout}>Çıkış yap</button></main>;

  function toggleFolder(folderId: string) {
    setCollapsedFolders(current => {
      const next = new Set(current);
      if (!next.delete(folderId)) next.add(folderId);
      return next;
    });
  }
  const renderDocument = (document: DocumentItem) => <li className="document" key={document.id}>
    <span className="file-icon" aria-hidden="true"><Icon name="file" /></span>
    <div>
      <span className="document-name" title={document.original_filename}>{document.original_filename}</span>
      <div className="document-meta">
        <span className={`status ${document.status}`}>{STATUS_LABELS[document.status]}</span>
        <span>{formatSize(document.size_bytes)}</span>
        <span>{formatDate(document.created_at)}</span>
      </div>
      {document.status === "failed" && document.error_message && <p className="document-error">{document.error_message}</p>}
      {document.status === "failed" && <button className="retry-button" disabled={retryingDocumentId !== null} onClick={() => void retryDocument(document.id)}><Icon name="retry" />{retryingDocumentId === document.id ? "Başlatılıyor…" : "Yeniden dene"}</button>}
    </div>
    <button type="button" className={`folder-button${folderMenu?.documentId === document.id ? " open" : ""}`} aria-haspopup="menu" aria-expanded={folderMenu?.documentId === document.id} aria-label="Klasöre taşı" title="Klasöre taşı" onClick={event => openFolderMenu(document.id, event.currentTarget)}><Icon name="folder" /></button>
  </li>;
  const hasReadyDocument = documents.some(document => document.status === "ready");
  const closeOverlays = () => {
    if (window.innerWidth <= 720) setSidebarOpen(false);
    if (window.innerWidth <= 1050) setLibraryOpen(false);
  };

  return <main className={`app${sidebarOpen ? "" : " no-sidebar"}${libraryOpen ? "" : " no-library"}`}>
    <aside id="conversation-sidebar" className="sidebar" hidden={!sidebarOpen}>
      <button className="home-link" onClick={() => setStarted(false)}><Icon name="home" />Ana sayfa</button>
      <button className="button primary new-chat" onClick={() => { activeConversationId.current = null; setActive(null); closeOverlays(); }}><Icon name="plus" />Yeni konuşma</button>
      <h2 className="sidebar-heading">Konuşmalar</h2>
      <nav className="conversation-list" aria-label="Konuşmalar">
        {conversations.length ? conversations.map(item => <button key={item.id} className={`conversation-item${active?.id === item.id ? " active" : ""}`} aria-current={active?.id === item.id ? "page" : undefined} onClick={() => { closeOverlays(); void openConversation(item); }}>
          <span className="conversation-title">{item.title ?? "Başlıksız konuşma"}</span>
          <span className="conversation-date">{formatDate(item.updated_at)}</span>
        </button>) : <p className="sidebar-empty">Sorduğunuz sorular burada listelenir.</p>}
      </nav>
      <div className="account">
        <span className="avatar" aria-hidden="true">{session.user.email[0].toUpperCase()}</span>
        <span className="account-email" title={session.user.email}>{session.user.email}</span>
        <button className="icon-button" title="Çıkış yap" aria-label="Çıkış yap" onClick={logout}><Icon name="logout" /></button>
      </div>
    </aside>
    <section className="workspace">
      <header className="workspace-header">
        <button className="icon-button" type="button" aria-controls="conversation-sidebar" aria-expanded={sidebarOpen} aria-label={sidebarOpen ? "Konuşma panelini kapat" : "Konuşma panelini aç"} title={sidebarOpen ? "Konuşma panelini kapat" : "Konuşma panelini aç"} onClick={() => setSidebarOpen(value => !value)}><Icon name="panelLeft" /></button>
        <h1 className="workspace-title">{active?.title ?? "Yeni konuşma"}</h1>
        <div className="header-actions">
          <button className="button soft" onClick={() => fileInput.current?.click()} disabled={uploading} aria-label="PDF yükle"><Icon name="upload" /><span>{uploading ? "Yükleniyor…" : "PDF yükle"}</span></button>
          <button className="icon-button" type="button" aria-controls="document-sidebar" aria-expanded={libraryOpen} aria-label={libraryOpen ? "Doküman panelini kapat" : "Doküman panelini aç"} title={libraryOpen ? "Doküman panelini kapat" : "Doküman panelini aç"} onClick={() => setLibraryOpen(value => !value)}><Icon name="panelRight" /></button>
          <input ref={fileInput} hidden type="file" accept="application/pdf,.pdf" onChange={event => void upload(event.target.files?.[0])} />
        </div>
      </header>
      {error && <div className="alert" role="alert"><span>{error}</span><button className="icon-button" aria-label="Uyarıyı kapat" onClick={() => setError("")}><Icon name="close" /></button></div>}
      <div className="content">
        {!visibleMessages.length ? <section className="welcome">
          <h2>Ne öğrenmek istersiniz?</h2>
          <p>{hasReadyDocument
            ? "Dokümanlarınızla ilgili bir soru yazın. Her cevabın altında kullanılan sayfaları görürsünüz."
            : "Başlamak için bir PDF yükleyin. Doküman işlendiğinde sorularınızı yanıtlamaya hazır olur."}</p>
          <div className="suggestions">{SUGGESTIONS.map(item => <button key={item.title} className="suggestion" onClick={() => setQuestion(item.question)}><b>{item.title}</b><span>{item.hint}</span></button>)}</div>
        </section> : <div className="message-list">
          {visibleMessages.map(message => <article key={message.id} className={`message ${message.role}`} aria-label={message.role === "user" ? "Sorunuz" : "Asistanın cevabı"}>
            {message.role === "user"
              ? <div className="bubble">{message.content}</div>
              : <><MessageContent content={message.content} /><SourceList sources={message.sources} /></>}
          </article>)}
          {asking && pendingMessage?.conversationId === (active?.id ?? null) && <div className="thinking" role="status"><span className="dots" aria-hidden="true"><i /><i /><i /></span>Kaynaklar taranıyor</div>}
          <div ref={conversationEnd} />
        </div>}
      </div>
      <footer className="composer-area">
        {folders.length > 0 && <div className="folder-chips" aria-label="Klasöre atıf yap">{folders.map(folder => <button type="button" key={folder.id} className="folder-chip" onClick={() => mentionFolder(folder)}>@{folder.name}</button>)}</div>}
        <form className="composer" onSubmit={ask}>
          <textarea value={question} onChange={event => setQuestion(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} placeholder="Dokümanlarınız hakkında bir soru sorun…" aria-label="Sorunuz" rows={1} />
          <button className="send-button" disabled={asking || !question.trim()} aria-label="Gönder" title="Gönder"><Icon name="send" /></button>
        </form>
        <p className="composer-note">Yanıtlar yalnızca yüklediğiniz dokümanlara dayanır.</p>
      </footer>
    </section>
    <aside id="document-sidebar" className="library" hidden={!libraryOpen}>
      <div className="library-head"><h2>Dokümanlar</h2><span className="count">{documents.length}</span></div>
      <button className="button soft library-folder" onClick={() => setFolderModalFor(null)}><Icon name="folder" />Klasör oluştur</button>
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
              <button type="button" className="folder-delete" aria-label={`${folder.name} klasörünü sil`} title="Klasörü sil" onClick={() => void removeFolder(folder)}><Icon name="close" /></button>
            </div>
            {open && (folderDocuments.length
              ? <ul className="folder-documents">{folderDocuments.map(renderDocument)}</ul>
              : <p className="folder-empty">Bu klasör boş.</p>)}
          </section>;
        })}
        {documents.some(item => !item.folder_id) && <ul className="folder-documents loose">{documents.filter(item => !item.folder_id).map(renderDocument)}</ul>}
      </div> : <div className="library-empty"><p>Henüz doküman yok.</p><p>Yüklediğiniz PDF’ler burada listelenir.</p></div>}
      <button className="button soft library-upload" onClick={() => fileInput.current?.click()} disabled={uploading}><Icon name="plus" />Doküman ekle</button>
    </aside>
    {folderMenu && menuDocument && <div className="folder-menu" role="menu" style={{ top: folderMenu.top, bottom: folderMenu.bottom, right: folderMenu.right }}>
      {folders.map(folder => <button key={folder.id} type="button" role="menuitem" onClick={() => { setFolderMenu(null); void moveDocument(menuDocument.id, menuDocument.folder_id === folder.id ? null : folder.id); }}>
        <Icon name="folder" /><span>{folder.name}</span>{menuDocument.folder_id === folder.id && <span className="folder-menu-check"><Icon name="check" /></span>}
      </button>)}
      {folders.length > 0 && <hr />}
      <button type="button" role="menuitem" className="folder-menu-create" onClick={() => { setFolderMenu(null); setFolderModalFor(menuDocument.id); }}><Icon name="plus" /><span>Yeni klasör oluştur</span></button>
    </div>}
    {folderModalFor !== undefined && <FolderModal onClose={closeFolderModal} onCreate={addFolder} />}
    <button className="scrim" aria-label="Paneli kapat" tabIndex={-1} onClick={closeOverlays} />
  </main>;
}

export default App;
