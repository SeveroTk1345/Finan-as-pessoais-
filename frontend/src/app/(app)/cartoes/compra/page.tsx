"use client";

import { useSearchParams } from "next/navigation";
import { type FormEvent, Suspense, useState } from "react";

import { useShell } from "@/components/Shell";
import {
  BackLink, Badge, ConfirmButton, DateText, ErrorBox, FormError, Loading, Money, MoneyInput, PageHeader, Situation, Stat, SubmitButton,
} from "@/components/ui";
import { api } from "@/lib/api";
import { formatCents } from "@/lib/format";
import { useApi, useSubmit } from "@/lib/hooks";

type Purchase = {
  id: string;
  card_id: string;
  card_name: string;
  kind: string;
  description: string;
  category_name: string | null;
  purchase_date: string;
  total_cents: number;
  installments_count: number;
  status: string;
  net_cents: number;
  installments: { id: string; number: number; amount_cents: number; invoice_due_date: string; status: string }[];
  credits: { id: string; kind: string; description: string; credit_date: string; invoice_due_date: string; amount_cents: number }[];
};

function Refund({ p, onDone }: { p: Purchase; onDone: () => void }) {
  const { online, flash } = useShell();
  const submit = useSubmit();
  const [amount, setAmount] = useState<number | null>(null);
  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const ok = await submit.run((key) => api.create(`/compras/${p.id}/estornar`, { amount_cents: amount }, key));
    if (ok) {
      flash("Estorno registrado na fatura aberta.");
      setAmount(null);
      onDone();
    }
  };
  return (
    <details className="card more">
      <summary>Registrar estorno (devolução parcial)</summary>
      <form className="stack" style={{ marginTop: 8 }} onSubmit={onSubmit} noValidate>
        <FormError error={submit.error} />
        <MoneyInput label="Valor estornado" cents={amount} onChange={setAmount} error={submit.fields.amount_cents}
          hint={`Até ${formatCents(p.net_cents)}.`} />
        <SubmitButton busy={submit.busy} online={online}>Registrar estorno</SubmitButton>
      </form>
    </details>
  );
}

function Detail({ id }: { id: string }) {
  const { online, flash } = useShell();
  const purchase = useApi<Purchase>(`/compras/${id}`);
  const [error, setError] = useState<string | null>(null);
  if (purchase.state === "loading") return <Loading />;
  if (purchase.state === "error") return <ErrorBox message={purchase.message} onRetry={purchase.reload} />;
  const p = purchase.data;
  const changeable = p.status === "ativa" && p.kind !== "parcelamento_fatura";
  return (
    <div className="stack-lg">
      <BackLink href={`/cartoes/detalhe/?id=${p.card_id}`}>{p.card_name}</BackLink>
      <PageHeader title={p.description} subtitle={<>Compra de <DateText iso={p.purchase_date} />{p.category_name ? ` · ${p.category_name}` : ""}</>} />
      <div className="card stack">
        {p.status === "cancelada" ? <Badge tone="warn">Compra cancelada</Badge> : null}
        <div className="grid-2">
          <Stat size="md" label="Valor da compra" cents={p.total_cents}
            help={p.installments_count > 1 ? `${p.installments_count} parcelas` : "À vista"} />
          <Stat size="md" label="Valor que continua contando" cents={p.net_cents} help="Depois de estornos e cancelamentos." />
        </div>
      </div>
      <FormError error={error} />
      <section className="stack">
        <h2>Parcelas</h2>
        <ul className="list">
          {p.installments.map((i) => (
            <li key={i.id} className="list-row">
              <span className="main">
                <span className="title">Parcela {i.number} de {p.installments_count}</span>
                <span className="sub">Fatura de <DateText iso={i.invoice_due_date} /></span>
              </span>
              <span style={{ textAlign: "right" }}>
                <Money cents={i.amount_cents} className="amount" />
                {i.status === "cancelada" ? <span style={{ display: "block" }}><Situation value="cancelada" /></span> : null}
              </span>
            </li>
          ))}
        </ul>
      </section>
      {p.credits.length > 0 ? (
        <section className="stack">
          <h2>Estornos e créditos</h2>
          <ul className="list">
            {p.credits.map((c) => (
              <li key={c.id} className="list-row">
                <span className="main"><span className="title">{c.description}</span>
                  <span className="sub"><DateText iso={c.credit_date} /> · na fatura de <DateText iso={c.invoice_due_date} /></span></span>
                <Money cents={-c.amount_cents} className="amount" />
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {changeable && p.net_cents > 0 ? <Refund p={p} onDone={purchase.reload} /> : null}
      {changeable ? (
        <ConfirmButton label="Cancelar compra" title="Cancelar esta compra?"
          message={<p>Parcelas ainda não faturadas são canceladas. O que já foi cobrado volta como crédito na fatura aberta. O histórico fica guardado.</p>}
          confirmLabel="Sim, cancelar" disabled={!online}
          onConfirm={async () => {
            try {
              await api.post(`/compras/${id}/cancelar`);
              flash("Compra cancelada.");
              purchase.reload();
            } catch (e) {
              setError(e instanceof Error ? e.message : "Erro.");
            }
          }} />
      ) : null}
      {p.kind === "parcelamento_fatura" ? <p className="muted">Estas parcelas fazem parte de um parcelamento de fatura. Acompanhe em Dívidas.</p> : null}
    </div>
  );
}

function Inner() {
  const id = useSearchParams().get("id");
  if (!id) return <ErrorBox message="Compra não informada." />;
  return <Detail id={id} />;
}

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <Inner />
    </Suspense>
  );
}
