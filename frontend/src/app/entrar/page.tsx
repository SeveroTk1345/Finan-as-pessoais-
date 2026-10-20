"use client";

import { type FormEvent, useEffect, useState } from "react";

import { Checkbox, FormError, TextInput } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useServerOnline } from "@/lib/hooks";
import { loginWithPasskey, passkeyErrorMessage, passkeySupported } from "@/lib/passkey";

export default function LoginPage() {
  const online = useServerOnline();
  const [usuario, setUsuario] = useState("");
  const [senha, setSenha] = useState("");
  const [manter, setManter] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [biometric, setBiometric] = useState(false);

  useEffect(() => {
    document.documentElement.dataset.ready = "1";
  }, []);

  useEffect(() => {
    passkeySupported().then(setBiometric);
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

  const withBiometrics = async () => {
    setBusy(true);
    setError(null);
    try {
      await loginWithPasskey(manter);
      window.location.replace("/");
    } catch (err) {
      setError(passkeyErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="content" style={{ maxWidth: 460, paddingTop: 48 }}>
      <form className="stack-lg" onSubmit={submit}>
        <div className="page-head">
          <h1>Finanças</h1>
          <p className="muted">
            {biometric ? "Entre com a digital ou o rosto, ou com usuário e senha." : "Entre com seu usuário e sua senha."}
          </p>
        </div>
        {!online ? (
          <div className="notice neg" role="alert">
            <strong>Sem conexão com o servidor</strong>
            Verifique a internet e tente de novo.
          </div>
        ) : null}
        <FormError error={error} />
        {biometric ? (
          <div className="stack">
            <button type="button" className="btn block" onClick={withBiometrics} disabled={busy || !online}>
              Entrar com digital ou rosto
            </button>
            <p className="small muted">Funciona se você já ativou neste aparelho, em Mais → Perfil e segurança.</p>
            <p className="divider-text muted">ou use usuário e senha</p>
          </div>
        ) : null}
        <div className="stack">
          <TextInput label="Usuário" value={usuario} onChange={setUsuario} autoComplete="username" maxLength={100} />
          <TextInput label="Senha" type="password" value={senha} onChange={setSenha} autoComplete="current-password" maxLength={200} />
          <Checkbox label="Manter conectado neste aparelho" checked={manter} onChange={setManter} />
          <p className="small muted">
            Use essa opção só no seu próprio celular ou computador. Em aparelho compartilhado, deixe desmarcado e toque em
            “Sair” ao terminar.
          </p>
        </div>
        <button type="submit" className={biometric ? "btn secondary block" : "btn block"} disabled={busy || !usuario || !senha}>
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
