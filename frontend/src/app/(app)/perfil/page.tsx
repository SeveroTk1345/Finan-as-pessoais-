"use client";

import { type FormEvent, useEffect, useState } from "react";

import { useShell } from "@/components/Shell";
import { BackLink, ConfirmButton, DateText, ErrorBox, FormError, Loading, PageHeader, SubmitButton, TextInput } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { activatePasskey, guessDeviceName, type PasskeyItem, passkeyErrorMessage, passkeySupported } from "@/lib/passkey";

function Biometrics() {
  const { online, flash } = useShell();
  const list = useApi<PasskeyItem[]>("/auth/digital");
  const [supported, setSupported] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    passkeySupported().then(setSupported);
  }, []);

  const activate = async () => {
    setBusy(true);
    setError(null);
    try {
      await activatePasskey(guessDeviceName(navigator.userAgent));
      flash("Pronto! Da próxima vez, entre com a digital ou o rosto.");
      list.reload();
    } catch (err) {
      setError(passkeyErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (item: PasskeyItem) => {
    await api.delete(`/auth/digital/${item.id}`);
    flash(`${item.nome} removido. Nele, será preciso usar usuário e senha.`);
    list.reload();
  };

  return (
    <section className="card stack" id="digital" aria-labelledby="digital-titulo">
      <h2 id="digital-titulo">Entrar com digital ou rosto</h2>
      <p className="muted">
        Ative em cada celular ou computador seu. Depois, basta tocar no sensor ou olhar para a câmera, sem digitar a senha.
        A digital e o rosto ficam só no aparelho; o aplicativo nunca os recebe.
      </p>
      <FormError error={error} />
      {list.state === "loading" ? <Loading /> : null}
      {list.state === "error" ? <ErrorBox message={list.message} onRetry={list.reload} /> : null}
      {list.state === "ready" && list.data.length > 0 ? (
        <ul className="list" aria-label="Aparelhos ativados">
          {list.data.map((p) => (
            <li key={p.id} className="list-row">
              <span className="main">
                <span className="title">{p.nome}</span>
                <span className="sub">
                  Ativado em <DateText iso={p.criada_em} />
                  {p.usada_em ? <> · último uso em <DateText iso={p.usada_em} /></> : null}
                </span>
              </span>
              <ConfirmButton label="Remover" title={`Remover ${p.nome}?`} confirmLabel="Remover" disabled={!online}
                message="Nesse aparelho, para entrar, será preciso usar usuário e senha. Você pode ativar de novo depois."
                onConfirm={() => remove(p)} />
            </li>
          ))}
        </ul>
      ) : null}
      {list.state === "ready" && list.data.length === 0 ? <p>Nenhum aparelho ativado ainda.</p> : null}
      {supported === false ? (
        <p className="small muted">
          Este aparelho ou navegador não oferece digital nem rosto. No iPhone, use o Safari; no Android, o Chrome.
        </p>
      ) : null}
      {supported ? (
        <button type="button" className="btn block" onClick={activate} disabled={busy || !online}>
          {busy ? "Aguardando o aparelho…" : "Ativar neste aparelho"}
        </button>
      ) : null}
    </section>
  );
}

export default function ProfilePage() {
  const { me, online, flash } = useShell();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (next !== repeat) {
      setError("A nova senha e a repetição estão diferentes.");
      setFields({ repetir: "Digite igual à nova senha." });
      return;
    }
    setBusy(true);
    setError(null);
    setFields({});
    try {
      await api.post("/auth/trocar-senha", { senha_atual: current, nova_senha: next });
      flash("Senha trocada. Outros aparelhos conectados na sua conta foram desconectados.");
      setCurrent("");
      setNext("");
      setRepeat("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro.");
      setFields(err instanceof ApiError ? err.fields : {});
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack-lg">
      <BackLink href="/mais/">Mais</BackLink>
      <PageHeader title="Perfil e segurança" subtitle={<>Conectado como <strong>{me.nome}</strong> (usuário {me.usuario}).</>} />
      <form className="card stack" onSubmit={onSubmit} noValidate>
        <h2>Trocar senha</h2>
        <FormError error={error} />
        <TextInput label="Senha atual" type="password" value={current} onChange={setCurrent} autoComplete="current-password" maxLength={200} error={fields.senha_atual} />
        <TextInput label="Nova senha" type="password" value={next} onChange={setNext} autoComplete="new-password" maxLength={200} error={fields.nova_senha}
          hint="Pelo menos 10 caracteres. Uma frase fácil de lembrar funciona bem." />
        <TextInput label="Repita a nova senha" type="password" value={repeat} onChange={setRepeat} autoComplete="new-password" maxLength={200} error={fields.repetir} />
        <SubmitButton busy={busy} online={online}>Trocar senha</SubmitButton>
      </form>
      <Biometrics />
      <section className="card stack">
        <h2>Sair</h2>
        <p className="muted">Em aparelho compartilhado, sempre toque em “Sair” no alto da tela ao terminar.</p>
      </section>
    </div>
  );
}
