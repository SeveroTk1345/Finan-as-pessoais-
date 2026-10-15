"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, Suspense, useState } from "react";

import { useShell } from "@/components/Shell";
import {
  BackLink, Checkbox, ConfirmButton, DateInput, DateText, Empty, ErrorBox, FormError, Loading, Money, MoneyInput,
  PageHeader, Segmented, Stat, SubmitButton, TextInput,
} from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { todayInSaoPaulo } from "@/lib/dates";
import { formatCents } from "@/lib/format";
import { useApi, useSubmit } from "@/lib/hooks";
import { ACCOUNT_KINDS, TX_KINDS } from "@/lib/options";
import type { Account, Transaction } from "@/lib/types";

function AdjustForm({ account, onDone }: { account: Account; onDone: () => void }) {
  const { online, flash } = useShell();
  const submit = useSubmit();
  const [real, setReal] = useState<number | null>(null);
  const [sign, setSign] = useState<"positivo" | "negativo">("positivo");
  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const cents = (real ?? 0) * (sign === "negativo" ? -1 : 1);
    const ok = await submit.run((key) =>
      api.create(`/contas/${account.id}/ajustar-saldo`, { real_balance_cents: cents, on: todayInSaoPaulo() }, key),
    );
    if (ok) {
      flash("Saldo conferido e ajustado.");
      onDone();
    }
  };
  return (
    <form className="card stack" onSubmit={onSubmit} noValidate>
      <h2>Conferir saldo com o banco</h2>
      <p className="muted small">
        Informe o saldo que aparece no banco hoje. Se for diferente, o app registra um ajuste com a diferença (não conta como receita
        nem despesa).
      </p>
      <FormError error={submit.error} />
      <MoneyInput label="Saldo real hoje" cents={real} onChange={setReal} allowZero />
      <Segmented label="O saldo está" value={sign} onChange={setSign}
        options={[{ value: "positivo", label: "Positivo" }, { value: "negativo", label: "Negativo" }]} />
      <SubmitButton busy={submit.busy} online={online}>Conferir e ajustar</SubmitButton>
    </form>
  );
}

function EditForm({ account, onDone }: { account: Account; onDone: () => void }) {
  const { online, flash } = useShell();
  const [name, setName] = useState(account.name);
  const [institution, setInstitution] = useState(account.institution ?? "");
  const [initial, setInitial] = useState<number | null>(Math.abs(account.initial_balance_cents));
  const [sign, setSign] = useState<"positivo" | "negativo">(account.initial_balance_cents < 0 ? "negativo" : "positivo");
  const [date, setDate] = useState(account.initial_balance_date);
  const [daily, setDaily] = useState(account.daily_use);
  const [error, setError] = useState<string | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.patch(`/contas/${account.id}`, {
        name, institution: institution || null, initial_balance_cents: (initial ?? 0) * (sign === "negativo" ? -1 : 1),
        initial_balance_date: date, daily_use: daily, version: account.version,
      });
      flash("Conta atualizada.");
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao salvar.");
      setFields(err instanceof ApiError ? err.fields : {});
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="stack" onSubmit={onSubmit} noValidate>
      <FormError error={error} />
      <TextInput label="Nome" value={name} onChange={setName} maxLength={80} error={fields.name} />
      <TextInput label="Banco ou instituição" value={institution} onChange={setInstitution} maxLength={80} />
      <MoneyInput label="Saldo inicial" cents={initial} onChange={setInitial} allowZero error={fields.initial_balance_cents} />
      <Segmented label="O saldo inicial estava" value={sign} onChange={setSign}
        options={[{ value: "positivo", label: "Positivo" }, { value: "negativo", label: "Negativo" }]} />
      <DateInput label="Data do saldo inicial" value={date} onChange={setDate} error={fields.initial_balance_date} />
      <Checkbox label="Contar no dinheiro disponível para o dia a dia" checked={daily} onChange={setDaily} />
      <SubmitButton busy={busy} online={online}>Salvar alterações</SubmitButton>
    </form>
  );
}

function Detail({ id }: { id: string }) {
  const router = useRouter();
  const { online, flash } = useShell();
  const acc = useApi<Account>(`/contas/${id}`);
  const txs = useApi<{ items: Transaction[]; total: number }>(`/lancamentos?conta=${id}&limite=50`);
  const [error, setError] = useState<string | null>(null);
  if (acc.state === "loading") return <Loading />;
  if (acc.state === "error") return <ErrorBox message={acc.message} onRetry={acc.reload} />;
  const a = acc.data;
  const refresh = () => {
    acc.reload();
    txs.reload();
  };
  const toggleActive = async () => {
    try {
      await api.patch(`/contas/${id}`, { is_active: !a.is_active, version: a.version });
      flash(a.is_active ? "Conta desativada. O histórico continua guardado." : "Conta reativada.");
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro.");
    }
  };
  const remove = async () => {
    try {
      await api.delete(`/contas/${id}`);
      flash("Conta excluída.");
      router.push("/contas/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro.");
    }
  };

  return (
    <div className="stack-lg">
      <BackLink href="/contas/">Contas</BackLink>
      <PageHeader title={a.name} subtitle={`${ACCOUNT_KINDS[a.kind]}${a.institution ? ` · ${a.institution}` : ""}`} />
      <div className="card">
        <Stat label="Saldo atual" cents={a.balance_cents}
          help={<>Saldo inicial de {formatCents(a.initial_balance_cents)} em <DateText iso={a.initial_balance_date} />, mais os lançamentos.</>} />
      </div>
      <FormError error={error} />
      <div className="actions">
        <Link className="btn" href={`/lancamentos/novo/?tipo=despesa&conta=${id}`}>+ Despesa</Link>
        <Link className="btn secondary" href={`/lancamentos/novo/?tipo=receita&conta=${id}`}>+ Receita</Link>
        <Link className="btn secondary" href="/lancamentos/novo/?tipo=transferencia">Transferir</Link>
      </div>

      <section className="stack" aria-labelledby="hist">
        <h2 id="hist">Movimentações recentes</h2>
        {txs.state === "loading" ? <Loading /> : txs.state === "error" ? <ErrorBox message={txs.message} onRetry={txs.reload} /> :
          txs.data.items.length === 0 ? <Empty title="Sem movimentações">Registre uma receita ou despesa nesta conta.</Empty> : (
            <ul className="list">
              {txs.data.items.map((t) => (
                <li key={t.id}>
                  <Link className="list-row" href={`/lancamentos/detalhe/?id=${t.id}`}>
                    <span className="main">
                      <span className="title">{t.description}</span>
                      <span className="sub"><DateText iso={t.tx_date} /> · {TX_KINDS[t.kind] ?? t.kind}</span>
                    </span>
                    <Money cents={t.direction === "entrada" ? t.amount_cents : -t.amount_cents} signed className="amount" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        {txs.state === "ready" && txs.data.total > txs.data.items.length ? (
          <Link className="btn ghost" href="/lancamentos/">Ver todas em Receitas e despesas</Link>
        ) : null}
      </section>

      {a.is_active ? <AdjustForm account={a} onDone={refresh} /> : null}

      <details className="card more">
        <summary>Editar conta</summary>
        <div style={{ marginTop: 8 }}><EditForm key={a.version} account={a} onDone={refresh} /></div>
      </details>

      <div className="grid-2">
        <ConfirmButton label={a.is_active ? "Desativar conta" : "Reativar conta"} tone="secondary"
          title={a.is_active ? "Desativar esta conta?" : "Reativar esta conta?"}
          message={a.is_active ? <p>Ela some das listas e do dinheiro disponível. Nada é apagado.</p> : <p>Ela volta a aparecer nas listas.</p>}
          confirmLabel={a.is_active ? "Desativar" : "Reativar"} onConfirm={toggleActive} disabled={!online} />
        {a.tx_count === 0 || txs.state === "ready" && txs.data.total === 0 ? (
          <ConfirmButton label="Excluir conta" title="Excluir esta conta?" message={<p>Esta conta não tem lançamentos e será apagada.</p>}
            confirmLabel="Excluir" onConfirm={remove} disabled={!online} />
        ) : null}
      </div>
    </div>
  );
}

function Inner() {
  const id = useSearchParams().get("id");
  if (!id) return <ErrorBox message="Conta não informada." />;
  return <Detail id={id} />;
}

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <Inner />
    </Suspense>
  );
}
