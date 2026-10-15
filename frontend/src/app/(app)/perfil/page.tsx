"use client";

import { type FormEvent, useState } from "react";

import { useShell } from "@/components/Shell";
import { BackLink, FormError, PageHeader, SubmitButton, TextInput } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

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
      <section className="card stack">
        <h2>Sair</h2>
        <p className="muted">Em aparelho compartilhado, sempre toque em “Sair” no alto da tela ao terminar.</p>
      </section>
    </div>
  );
}
