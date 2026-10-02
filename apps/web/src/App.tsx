import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api } from "./api";
import type { AuthSession, Conversation, ConversationDetail, DocumentItem, Message, Source } from "./types";

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

function LandingScreen({ onStart, hasSession }: { onStart: () => void; hasSession: boolean }) {
  return <main className="landing-shell">
    <nav className="landing-nav">
      <span className="nav-note">AI DOCUMENT INTELLIGENCE</span>
      <button onClick={onStart}>{hasSession ? "Uygulamaya dön" : "Giriş yap"}</button>
    </nav>
    <div className="landing-glow glow-one" /><div className="landing-glow glow-two" />
    <section className="landing-copy">
      <p className="landing-kicker"><i /> Kurumsal bilginin yeni formu</p>
      <h1>Bilginiz.<br /><em>Canlı, bağlantılı</em><br />ve erişilebilir.</h1>
      <p>Dağınık dokümanlarınızı kaynaklarıyla konuşabilen güvenilir bir bilgi merkezine dönüştürün.</p>
      <button className="start-button" onClick={onStart}><span>{hasSession ? "Dokümanlara git" : "Başla"}</span><b>↗</b></button>
    </section>
    <section className="landing-visual" aria-hidden="true">
      <div className="visual-orbit orbit-a" /><div className="visual-orbit orbit-b" />
      <img src="/atlas-knowledge-core.png" alt="" />
      <span className="visual-label label-one">15 CHUNKS INDEXED</span>
      <span className="visual-label label-two">SOURCE VERIFIED</span>
    </section>
    <footer className="landing-footer"><span>DOCUMENTS</span><span>KNOWLEDGE</span><span>CONVERSATIONS</span></footer>
  </main>;
}

function AuthScreen({ onAuthenticated }: { onAuthenticated: (session: AuthSession) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
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
  return <div className="sources">{sources.map((source, index) => <details key={source.chunk_id}>
    <summary><span>{index + 1}</span>{source.filename} · Sayfa {source.page_number}<b>%{Math.round(source.similarity * 100)}</b></summary>
    <p>{source.content}</p>
  </details>)}</div>;
}

function renderInlineFormatting(content: string): ReactNode[] {
  return content.split(/(\*\*[^*]+\*\*)/g).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}

function MessageContent({ content }: { content: string }) {
  return <div className="message-content">{content.split("\n").map((line, index) => (
    <p key={`${index}-${line}`} className={/^\s*[-•]\s/.test(line) ? "bullet-line" : undefined}>
      {renderInlineFormatting(line)}
    </p>
  ))}</div>;
}

function App() {
  const [session, setSession] = useState<AuthSession | null>(readSession);
  const [started, setStarted] = useState(() => readSession() !== null);
  const [organizationId, setOrganizationId] = useState("");
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
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

  const refreshConversations = useCallback(async () => {
    if (!session || !organizationId) return;
    try {
      const result = await api.conversations(organizationId, session.access_token);
      setConversations(result.items);
    } catch (caught) { handleError(caught); }
  }, [session, organizationId, handleError]);

  const refresh = useCallback(async () => {
    await Promise.all([refreshDocuments(), refreshConversations()]);
  }, [refreshDocuments, refreshConversations]);

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

  if (!started) return <LandingScreen onStart={() => setStarted(true)} hasSession={session !== null} />;
  if (!session) return <AuthScreen onAuthenticated={authenticated} />;
  if (!organizationId) return <main className="empty-page"><h2>Bu hesaba bağlı bir organizasyon bulunamadı.</h2><button onClick={logout}>Çıkış yap</button></main>;

  return <main className="app-shell">
    <aside className="sidebar">
      <button className="home-link" onClick={() => setStarted(false)}><span>⌂</span> Ana sayfa</button>
      <button className="new-chat" onClick={() => { activeConversationId.current = null; setActive(null); }}><span>＋</span> Yeni konuşma</button>
      <div className="sidebar-title">Konuşmalar</div>
      <nav>{conversations.map(item => <button key={item.id} className={active?.id === item.id ? "active" : ""} onClick={() => void openConversation(item)}>
        <span className="chat-icon">◇</span><span><b>{item.title ?? "Başlıksız konuşma"}</b><small>{formatDate(item.updated_at)}</small></span>
      </button>)}</nav>
      <div className="user-card"><div className="avatar">{session.user.email[0].toUpperCase()}</div><div><b>{session.user.email.split("@")[0]}</b><small>{session.user.email}</small></div><button title="Çıkış yap" onClick={logout}>↗</button></div>
    </aside>
    <section className="workspace">
      <header><div><span className="status-dot" /> Bilgi merkezi aktif</div><div className="header-actions"><button onClick={() => fileInput.current?.click()} disabled={uploading}>⌁ {uploading ? "Yükleniyor…" : "PDF yükle"}</button><input ref={fileInput} hidden type="file" accept="application/pdf,.pdf" onChange={event => void upload(event.target.files?.[0])} /></div></header>
      {error && <div className="global-error">{error}<button onClick={() => setError("")}>×</button></div>}
      <div className="content">
        {!visibleMessages.length ? <section className="welcome">
          <p className="eyebrow">KAYNAKLARINIZA DAYALI YANITLAR</p><h1>Bugün neyi<br /><em>keşfedelim?</em></h1><p>Dokümanlarınızdaki bilgileri sorun; yanıtları kaynaklarıyla birlikte inceleyin.</p>
          <div className="suggestions"><button onClick={() => setQuestion("Dokümanlardaki en önemli noktaları özetle.")}><span>01</span><b>Genel bir özet çıkar</b><small>Belgelerdeki ana fikirleri keşfet</small></button><button onClick={() => setQuestion("Bu dokümanlarda hangi süreçler anlatılıyor?")}><span>02</span><b>Süreçleri bul</b><small>Adımları ve sorumlulukları listele</small></button></div>
        </section> : <section className="conversation-view"><div className="conversation-heading"><p className="eyebrow">KONUŞMA</p><h2>{active?.title ?? "Yeni konuşma"}</h2></div><div className="message-list">{visibleMessages.map(message => <article key={message.id} className={`message ${message.role}`}><div className="message-avatar" aria-hidden="true">{message.role === "user" ? session.user.email[0].toUpperCase() : "✦"}</div><div className="message-column"><div className="message-role">{message.role === "user" ? "Siz" : "Asistan"}</div><div className="message-body"><MessageContent content={message.content} /><SourceList sources={message.sources} /></div></div></article>)}{asking && pendingMessage?.conversationId === (active?.id ?? null) && <div className="thinking"><span className="message-avatar">✦</span><div><i /><i /><i /> Kaynaklar taranıyor</div></div>}<div ref={conversationEnd} /></div></section>}
      </div>
      <footer className="composer-area"><form className="composer" onSubmit={ask}><textarea value={question} onChange={event => setQuestion(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} placeholder="Dokümanlarınız hakkında bir soru sorun…" rows={1} /><button disabled={asking || !question.trim()} aria-label="Gönder">↑</button><div className="composer-note">Enter ile gönder · Shift + Enter ile yeni satır</div></form><p>Yanıtlar yalnızca yüklediğiniz dokümanlara dayanır ve kaynaklarıyla gösterilir.</p></footer>
    </section>
    <aside className="library"><div className="library-head"><div><p className="eyebrow">KÜTÜPHANE</p><h3>Dokümanlar</h3></div><span>{documents.length}</span></div><div className="document-list">{documents.length ? documents.map(document => <div className="document-card" key={document.id}><div className="pdf-icon">PDF</div><div><b title={document.original_filename}>{document.original_filename}</b><small>{(document.size_bytes / 1024).toFixed(0)} KB · {formatDate(document.created_at)}</small><span className={`status ${document.status}`} title={document.error_message ?? undefined}>{document.status === "ready" ? "Hazır" : document.status === "failed" ? "İşlenemedi" : document.status === "pending" ? "Sırada" : "İşleniyor"}</span>{document.status === "failed" && document.error_message && <small className="document-error">{document.error_message}</small>}{document.status === "failed" && <button className="retry-document" disabled={retryingDocumentId !== null} onClick={() => void retryDocument(document.id)}>{retryingDocumentId === document.id ? "Tekrar başlatılıyor…" : "Tekrar dene"}</button>}</div></div>) : <div className="empty-library"><div>⌁</div><p>Henüz doküman yok</p><small>İlk PDF’inizi yükleyin</small></div>}</div><button className="library-upload" onClick={() => fileInput.current?.click()} disabled={uploading}>＋ Doküman ekle</button></aside>
  </main>;
}

export default App;
