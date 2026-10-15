"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, Suspense, useState } from "react";

import { useShell } from "@/components/Shell";
import {
  BackLink,
  Badge,
  ConfirmButton,
  DateInput,
  DateText,
  ErrorBox,
  FormError,
  Loading,
  Money,
  MoneyInput,
  PageHeader,
  Select,
  SubmitButton,
  TextInput,
} from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { todayInSaoPaulo } from "@/lib/dates";
import { formatCents } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { TX_KINDS, useAccounts, useCategories } from "@/lib/options";
import type { Transaction } from "@/lib/types";

const EDITABLE = ["receita", "despesa", "reembolso", "ajuste"];

function EditForm({ t }: { t: Transaction }) {
  const router = useRouter();
  const { online, flash } = useShell();
  const accounts = useAccounts();
  const categories = useCategories(t.kind === "receita" ? "receita" : "despesa");
  const [amount, setAmount] = useState<number | null>(t.amount_cents);
  const [description, setDescription] = useState(t.description);
  const [accountId, setAccountId] = useState(t.account_id);
  const [categoryId, setCategoryId] = useState(t.category_id ?? "");
  const [date, setDate] = useState(t.tx_date);
  const [error, setError] = useState<string | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.patch(`/lancamentos/${t.id}`, {
        amount_cents: amount, description, account_id: accountId, tx_date: date,
        ...(t.kind === "ajuste" ? {} : { category_id: categoryId || null }), version: t.version,
      });
      flash("Alteração salva.");
      router.push("/lancamentos/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao salvar.");
      setFields(err instanceof ApiError ? err.fields : {});
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="stack" onSubmit={save} noValidate>
      <h2>Corrigir</h2>
      <FormError error={error} />
      <MoneyInput label="Valor" cents={amount} onChange={setAmount} error={fields.amount_cents} />
      <TextInput label="Descrição" value={description} onChange={setDescription} error={fields.description} />
      <Select label="Conta" value={accountId} onChange={setAccountId} options={accounts.options} error={fields.account_id} />
      {t.kind !== "ajuste" ? (
        <Select label="Categoria" value={categoryId} onChange={setCategoryId} options={categories.options} placeholder="Sem categoria" error={fields.category_id} />
      ) : null}
      <DateInput label="Data" value={date} onChange={setDate} max={todayInSaoPaulo()} error={fields.tx_date} />
      <SubmitButton busy={busy} online={online}>Salvar alteração</SubmitButton>
    </form>
  );
}

function Detail({ id }: { id: string }) {
  const router = useRouter();
  const { online, flash } = useShell();
  const tx = useApi<Transaction>(`/lancamentos/${id}`);
  const [error, setError] = useState<string | null>(null);

  if (tx.state === "loading") return <Loading />;
  if (tx.state === "error") return <ErrorBox message={tx.message} onRetry={tx.reload} />;
  const t = tx.data;
  const editable = t.status === "ativo" && EDITABLE.includes(t.kind);

  const cancel = async () => {
    try {
      await api.post(`/lancamentos/${id}/cancelar`);
      flash(t.kind === "transferencia" ? "Transferência cancelada (as duas contas foram corrigidas)." : "Lançamento cancelado.");
      router.push("/lancamentos/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao cancelar.");
    }
  };

  return (
    <div className="stack-lg">
      <BackLink href="/lancamentos/">Receitas e despesas</BackLink>
      <PageHeader title={t.description} subtitle={<>{TX_KINDS[t.kind] ?? t.kind} · <DateText iso={t.tx_date} /></>} />
      <div className="card stack">
        <p className="stat-value md"><Money cents={t.direction === "entrada" ? t.amount_cents : -t.amount_cents} signed /></p>
        <p>{t.account_name}{t.transfer_other_account_name ? ` ${t.direction === "saida" ? "→" : "←"} ${t.transfer_other_account_name}` : ""}</p>
        {t.status === "cancelado" ? <Badge tone="warn">Cancelado: não entra mais nos saldos</Badge> : null}
      </div>
      <FormError error={error} />

      {editable ? (
        <EditForm key={t.version} t={t} />
      ) : t.status === "ativo" && t.kind !== "investimento" ? (
        <p className="muted">Este lançamento faz parte de outra operação. Para corrigir, cancele e registre de novo.</p>
      ) : null}

      {t.status === "ativo" && t.kind !== "investimento" ? (
        <ConfirmButton label="Cancelar lançamento" title="Cancelar este lançamento?"
          message={<p>O valor de {formatCents(t.amount_cents)} deixa de contar nos saldos. O registro fica guardado no histórico como cancelado.</p>}
          confirmLabel="Sim, cancelar" onConfirm={cancel} disabled={!online} />
      ) : null}

      {t.history && t.history.length > 0 ? (
        <details className="card more">
          <summary>Histórico de alterações</summary>
          <ul className="list" style={{ marginTop: 8 }}>
            {t.history.map((h, i) => (
              <li key={i} className="list-row">
                <span className="main">
                  <span className="title">{h.action === "editar" ? "Alterado" : "Cancelado"}</span>
                  <span className="sub">{h.created_at.slice(0, 10).split("-").reverse().join("/")}</span>
                </span>
                {h.before_data && typeof h.before_data.amount_cents === "number" ? (
                  <span className="small">Antes: {formatCents(h.before_data.amount_cents)}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

function Inner() {
  const id = useSearchParams().get("id");
  if (!id) return <ErrorBox message="Lançamento não informado." />;
  return <Detail id={id} />;
}

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <Inner />
    </Suspense>
  );
}
