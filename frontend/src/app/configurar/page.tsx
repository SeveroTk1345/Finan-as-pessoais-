"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useState } from "react";

import { FormError, TextInput } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/hooks";

type Status = { habilitada: boolean; contas: number | null; maximo: number };

function useForm() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [done, setDone] = useState<string | null>(null);
  const run = async (fn: () => Promise<string>) => {
    setBusy(true);
    setError(null);
    setFields({});
    setDone(null);
    try {
      setDone(await fn());
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro.");
      setFields(e instanceof ApiError ? e.fields : {});
      return false;
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, fields, done, run, setError };
}

function CreateAccount({ code, onCreated, full }: { code: string; onCreated: () => void; full: boolean }) {
  const [usuario, setUsuario] = useState("");
  const [nome, setNome] = useState("");
  const [senha, setSenha] = useState("");
  const [repetir, setRepetir] = useState("");
  const f = useForm();
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (senha !== repetir) return f.setError("A senha e a repetição estão diferentes.");
    const ok = await f.run(async () => {
      const r = await api.post<{ usuario: string; nome: string }>("/configuracao/contas", { codigo: code, usuario, nome, senha });
      return `Conta de ${r.nome} criada (usuário ${r.usuario}). Entregue a senha pessoalmente; a pessoa pode trocar em Mais → Perfil e segurança.`;
    });
    if (ok) {
      setUsuario("");
      setNome("");
      setSenha("");
      setRepetir("");
      onCreated();
    }
  };
  return (
    <form className="card stack" onSubmit={submit} noValidate>
      <h2>Criar conta</h2>
      {full ? <p className="muted">As 3 contas já foram criadas.</p> : (
        <>
          <FormError error={f.error} />
          {f.done ? <div className="notice pos" role="status">{f.done}</div> : null}
          <TextInput label="Usuário (para entrar)" value={usuario} onChange={setUsuario} maxLength={40} error={f.fields.usuario}
            hint="Letras minúsculas, sem espaço. Ex.: ana" autoComplete="off" />
          <TextInput label="Nome (aparece no app)" value={nome} onChange={setNome} maxLength={60} error={f.fields.nome} />
          <TextInput label="Senha" type="password" value={senha} onChange={setSenha} maxLength={200} error={f.fields.senha}
            hint="Pelo menos 10 caracteres. Uma frase fácil de lembrar funciona bem." autoComplete="new-password" />
          <TextInput label="Repita a senha" type="password" value={repetir} onChange={setRepetir} maxLength={200} autoComplete="new-password" />
          <button type="submit" className="btn block" disabled={f.busy || !code}>{f.busy ? "Criando…" : "Criar conta"}</button>
        </>
      )}
    </form>
  );
}

function ResetPassword({ code }: { code: string }) {
  const [usuario, setUsuario] = useState("");
  const [senha, setSenha] = useState("");
  const [repetir, setRepetir] = useState("");
  const f = useForm();
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (senha !== repetir) return f.setError("A senha e a repetição estão diferentes.");
    const ok = await f.run(async () => {
      await api.post("/configuracao/redefinir-senha", { codigo: code, usuario, nova_senha: senha });
      return `Senha de ${usuario.trim().toLowerCase()} trocada. Os aparelhos conectados nessa conta foram desconectados.`;
    });
    if (ok) {
      setSenha("");
      setRepetir("");
    }
  };
  return (
    <form className="card stack" onSubmit={submit} noValidate>
      <h2>Alguém esqueceu a senha?</h2>
      <FormError error={f.error} />
      {f.done ? <div className="notice pos" role="status">{f.done}</div> : null}
      <TextInput label="Usuário" value={usuario} onChange={setUsuario} maxLength={40} error={f.fields.usuario} autoComplete="off" />
      <TextInput label="Nova senha" type="password" value={senha} onChange={setSenha} maxLength={200} error={f.fields.nova_senha}
        autoComplete="new-password" />
      <TextInput label="Repita a nova senha" type="password" value={repetir} onChange={setRepetir} maxLength={200} autoComplete="new-password" />
      <button type="submit" className="btn secondary block" disabled={f.busy || !code}>{f.busy ? "Trocando…" : "Trocar senha"}</button>
    </form>
  );
}

export default function SetupPage() {
  const status = useApi<Status>("/configuracao");
  const [code, setCode] = useState("");

  useEffect(() => {
    document.documentElement.dataset.ready = "1";
  }, []);

  return (
    <main className="content" style={{ maxWidth: 520, paddingTop: 40 }}>
      <div className="stack-lg">
        <div className="page-head">
          <h1>Configurar o aplicativo</h1>
          <p className="muted">Criar as contas das pessoas e trocar senha esquecida. Só quem administra tem o código.</p>
        </div>
        {status.state === "loading" ? <p className="muted">Carregando…</p> : null}
        {status.state === "error" ? <div className="notice neg" role="alert">{status.message}</div> : null}
        {status.state === "ready" && !status.data.habilitada ? (
          <div className="notice" role="status">
            <strong>Configuração desligada.</strong> Para ligar, defina FIN_SETUP_TOKEN no servidor.
          </div>
        ) : null}
        {status.state === "ready" && status.data.habilitada ? (
          <>
            <p><strong>{status.data.contas} de {status.data.maximo}</strong> contas criadas.</p>
            <div className="card stack">
              <TextInput label="Código de configuração" type="password" value={code} onChange={setCode} maxLength={200}
                autoComplete="off" hint="Está no painel do Render: Environment → FIN_SETUP_TOKEN." />
            </div>
            <CreateAccount code={code} onCreated={status.reload} full={(status.data.contas ?? 0) >= status.data.maximo} />
            <ResetPassword code={code} />
          </>
        ) : null}
        <p><Link href="/entrar/">Ir para a tela de entrada</Link></p>
      </div>
    </main>
  );
}
