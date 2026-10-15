"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useState } from "react";

import { api, onUnauthorized } from "@/lib/api";
import { useServerOnline } from "@/lib/hooks";

type Me = { id: string; usuario: string; nome: string };

type ShellCtx = {
  me: Me;
  online: boolean;
  flash: (message: string) => void;
};

const Ctx = createContext<ShellCtx | null>(null);

export function useShell(): ShellCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useShell fora do Shell");
  return v;
}

// Ícones simples em traço, sempre acompanhados de texto.
function Icon({ name }: { name: string }) {
  const paths: Record<string, string> = {
    home: "M3 11 12 4l9 7v9a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z",
    wallet: "M3 7h15a3 3 0 0 1 3 3v7a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3zm0 0V6a2 2 0 0 1 2-2h11M16 14h2",
    list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
    calendar: "M4 6h16v14H4zM4 10h16M8 3v4M16 3v4",
    debt: "M4 19h16M6 15V9M10 15V9M14 15V9M18 15V9M3 9l9-5 9 5",
    chart: "M4 20V10M10 20V4M16 20v-7M22 20H2",
    target: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zm0-5a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm0-3h.01",
    more: "M5 12h.01M12 12h.01M19 12h.01",
  };
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={paths[name] ?? ""} />
    </svg>
  );
}

const DESKTOP_NAV = [
  { href: "/", label: "Início", icon: "home" },
  { href: "/contas", label: "Contas", icon: "wallet" },
  { href: "/lancamentos", label: "Receitas e despesas", icon: "list" },
  { href: "/a-pagar", label: "Contas a pagar", icon: "calendar" },
  { href: "/dividas", label: "Dívidas e parcelas", icon: "debt" },
  { href: "/investimentos", label: "Investimentos", icon: "chart" },
  { href: "/planejamento", label: "Planejamento", icon: "target" },
  { href: "/mais", label: "Mais", icon: "more" },
];

const MOBILE_NAV = [
  { href: "/", label: "Início", icon: "home" },
  { href: "/lancamentos", label: "Lançamentos", icon: "list" },
  { href: "/a-pagar", label: "A pagar", icon: "calendar" },
  { href: "/investimentos", label: "Investir", icon: "chart" },
  { href: "/mais", label: "Mais", icon: "more" },
];

// Páginas que pertencem a "Mais" no celular.
const MORE_PAGES = ["/mais", "/contas", "/dividas", "/planejamento", "/cartoes", "/relatorios", "/categorias", "/perfil", "/exportar", "/ajuda"];

function isActive(pathname: string, href: string): boolean {
  const p = pathname.replace(/\/$/, "") || "/";
  if (href === "/") return p === "/";
  return p === href || p.startsWith(`${href}/`);
}

export function Shell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname() ?? "/";
  const online = useServerOnline();
  const [me, setMe] = useState<Me | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    onUnauthorized(() => router.replace("/entrar/"));
    api
      .get<Me>("/auth/eu")
      .then(setMe)
      .catch((e: unknown) => {
        if (e instanceof Error && "status" in e && (e as { status: number }).status === 401) {
          router.replace("/entrar/");
        } else {
          setFailed(e instanceof Error ? e.message : "Erro ao carregar.");
        }
      });
  }, [router]);

  useEffect(() => {
    // Voltar para uma página guardada pelo navegador (ex.: depois de sair) recarrega
    // e passa de novo pela verificação de sessão, sem reexibir dados antigos.
    const onShow = (e: PageTransitionEvent) => {
      if (e.persisted) window.location.reload();
    };
    window.addEventListener("pageshow", onShow);
    return () => window.removeEventListener("pageshow", onShow);
  }, []);

  useEffect(() => {
    if (!message) return;
    const t = setTimeout(() => setMessage(null), 6000);
    return () => clearTimeout(t);
  }, [message]);

  const flash = useCallback((m: string) => setMessage(m), []);

  useEffect(() => {
    // Sinaliza que a tela terminou de carregar (usado pelos testes automatizados).
    if (me) document.documentElement.dataset.ready = "1";
  }, [me]);

  const logout = async () => {
    try {
      await api.post("/auth/sair");
    } finally {
      // Limpa caches do service worker (só guardam a estrutura do app, mas por garantia).
      if ("caches" in window) {
        const keys = await caches.keys();
        await Promise.all(keys.filter((k) => k.startsWith("fin-dados")).map((k) => caches.delete(k)));
      }
      window.location.replace("/entrar/");
    }
  };

  if (!me) {
    return (
      <main className="content">
        {failed ? (
          <div className="notice neg" role="alert">
            <strong>Não foi possível abrir o aplicativo</strong>
            <p>{failed}</p>
            <button className="btn secondary" style={{ marginTop: 12 }} onClick={() => window.location.reload()}>
              Tentar de novo
            </button>
          </div>
        ) : (
          <p className="muted" aria-live="polite">Carregando…</p>
        )}
      </main>
    );
  }

  const mobileActive = (href: string) =>
    href === "/mais" ? MORE_PAGES.some((p) => isActive(pathname, p)) : isActive(pathname, href);

  return (
    <Ctx.Provider value={{ me, online, flash }}>
      <div className="app">
        <nav className="sidebar" aria-label="Menu principal">
          <Link href="/" className="brand">Finanças</Link>
          {DESKTOP_NAV.map((n) => (
            <Link key={n.href} href={n.href} className="navlink" aria-current={isActive(pathname, n.href) ? "page" : undefined}>
              <Icon name={n.icon} />
              {n.label}
            </Link>
          ))}
        </nav>
        <div>
          {!online ? (
            <div className="offline-bar" role="alert">
              Sem conexão com o servidor. Você pode olhar esta tela, mas nada novo será salvo até a conexão voltar.
            </div>
          ) : null}
          <header className="topbar">
            <Link href="/" className="brand">Finanças</Link>
            <div className="who">
              <span>
                Conectado como <strong>{me.nome}</strong>
              </span>
              <button type="button" className="btn secondary" style={{ minHeight: 44, padding: "0 14px" }} onClick={logout}>
                Sair
              </button>
            </div>
          </header>
          <main className="content" id="conteudo">
            {message ? (
              <div className="notice pos" role="status" style={{ marginBottom: 16 }}>
                <strong>✓ {message}</strong>
              </div>
            ) : null}
            {children}
          </main>
        </div>
        <nav className="bottombar" aria-label="Menu">
          {MOBILE_NAV.map((n) => (
            <Link key={n.href} href={n.href} aria-current={mobileActive(n.href) ? "page" : undefined}>
              <span className="nav-icon"><Icon name={n.icon} /></span>
              {n.label}
            </Link>
          ))}
        </nav>
      </div>
    </Ctx.Provider>
  );
}
