import { FormEvent, useState } from "react";
import { api } from "../api";
import type { AuthSession } from "../types";
import type { AuthMode } from "./LandingScreen";

export function AuthScreen({ onAuthenticated, initialMode }: { onAuthenticated: (session: AuthSession) => void; initialMode: AuthMode }) {
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
