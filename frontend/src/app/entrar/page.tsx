"use client";

import { type FormEvent, useEffect, useState } from "react";

import { Checkbox, FormError, TextInput } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useServerOnline } from "@/lib/hooks";

export default function LoginPage() {
  const online = useServerOnline();
  const [usuario, setUsuario] = useState("");
  const [senha, setSenha] = useState("");
  const [manter, setManter] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    document.documentElement.dataset.ready = "1";
  }, []);

  useEffect(() => {
    // Já conectado? Vai direto para o início.
    api.get("/auth/eu").then(() => window.location.replace("/")).catch(() => undefined);
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/auth/entrar", { usuario, senha, manter_conectado: manter });
      window.location.replace("/");
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : "Erro ao entrar.");
      setSenha("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="content" style={{ maxWidth: 460, paddingTop: 48 }}>
      <form className="stack-lg" onSubmit={submit}>
        <div className="page-head">
          <h1>Finanças</h1>
          <p className="muted">Entre com seu usuário e sua senha.</p>
        </div>
        {!online ? (
          <div className="notice neg" role="alert">
            <strong>Sem conexão com o servidor</strong>
            Verifique a internet e tente de novo.
          </div>
        ) : null}
        <FormError error={error} />
        <div className="stack">
          <TextInput label="Usuário" value={usuario} onChange={setUsuario} autoComplete="username" maxLength={100} />
          <TextInput label="Senha" type="password" value={senha} onChange={setSenha} autoComplete="current-password" maxLength={200} />
          <Checkbox label="Manter conectado neste aparelho" checked={manter} onChange={setManter} />
          <p className="small muted">
            Use essa opção só no seu próprio celular ou computador. Em aparelho compartilhado, deixe desmarcado e toque em
            “Sair” ao terminar.
          </p>
        </div>
        <button type="submit" className="btn block" disabled={busy || !usuario || !senha}>
          {busy ? "Entrando…" : "Entrar"}
        </button>
        <p className="small muted">
          Esqueceu a senha? Peça para quem administra o aplicativo criar uma nova. Por segurança, não existe recuperação
          automática.
        </p>
      </form>
    </main>
  );
}
