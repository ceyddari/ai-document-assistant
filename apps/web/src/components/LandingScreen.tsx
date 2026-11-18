import { useEffect, useRef } from "react";
import { Icon } from "./Icon";

export type AuthMode = "login" | "register";

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

export function LandingScreen({ onStart, hasSession }: { onStart: (mode?: AuthMode) => void; hasSession: boolean }) {
  const lotusRef = useLotusMotion();
  return <main className="landing-shell">
    <nav className="landing-nav">
      <span className="nav-note">AI DOCUMENT INTELLIGENCE</span>
      {/* Signed in, the hero button is the only way in; a second one here would repeat it. */}
      <div className="landing-actions">
        {!hasSession && <><HoverButton text="Giriş yap" onClick={() => onStart("login")} /><HoverButton text="Kayıt ol" onClick={() => onStart("register")} /></>}
      </div>
    </nav>
    <div className="landing-glow glow-one" /><div className="landing-glow glow-two" />
    <section className="landing-copy">
      <p className="landing-kicker"><i /> Bilginin yeni formu</p>
      <h1>Bilginiz.<br /><em>Canlı, bağlantılı</em><br />ve erişilebilir.</h1>
      <p>Dağınık dokümanlarınızı kaynaklarıyla konuşabilen güvenilir bir bilgi merkezine dönüştürün.</p>
      <button className="colorful-button" onClick={() => onStart()}>
        <span className="colorful-glow" aria-hidden="true" />
        <span className="colorful-content">{hasSession ? "Çalışma alanına git" : "Başla"}<Icon name="arrowUpRight" /></span>
      </button>
    </section>
    <section className="landing-visual" aria-hidden="true">
      <div className="visual-orbit orbit-a" /><div className="visual-orbit orbit-b" />
      <img ref={lotusRef} src="/atlas-knowledge-core.png" alt="" />
    </section>
    <footer className="landing-footer"><span>DOCUMENTS</span><span>KNOWLEDGE</span><span>CONVERSATIONS</span></footer>
  </main>;
}
