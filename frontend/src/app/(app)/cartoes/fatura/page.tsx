"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { type FormEvent, Suspense, useState } from "react";

import { useShell } from "@/components/Shell";
import {
  BackLink, DateInput, DateText, ErrorBox, FormError, Loading, Money, MoneyInput, NumberInput, PageHeader, Select, Situation, Stat,
  SubmitButton, useScrollToError,
} from "@/components/ui";
import { api } from "@/lib/api";
import { todayInSaoPaulo } from "@/lib/dates";
import { formatCents } from "@/lib/format";
import { useApi, useSubmit } from "@/lib/hooks";
import { useAccounts } from "@/lib/options";
import type { Invoice } from "@/lib/types";

type InvoiceDetail = Invoice & {
  card: { id: string; name: string };
  items: { id: string; number: number; amount_cents: number; status: string; purchase_id: string; description: string; purchase_date: string; installments_count: number; kind: string; category_name: string | null }[];
  credits: { id: string; kind: string; description: string; credit_date: string; amount_cents: number }[];
  payments: { id: string; amount_cents: number; tx_date: string; status: string; account_name: string }[];
};

function PayInvoice({ inv, onDone }: { inv: InvoiceDetail; onDone: () => void }) {
  const { online, flash } = useShell();
  const accounts = useAccounts();
  const submit = useSubmit();
  useScrollToError(submit.error);
  const [amount, setAmount] = useState<number | null>(inv.remaining_cents);
  const [accountId, setAccountId] = useState("");
  const [date, setDate] = useState(todayInSaoPaulo());
  const account = accountId || accounts.options[0]?.value || "";
  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const ok = await submit.run((key) =>
      api.create(`/cartoes/${inv.card.id}/faturas/${inv.due_date}/pagar`, { account_id: account, amount_cents: amount, tx_date: date }, key),
    );
    if (ok) {
      flash(amount === inv.remaining_cents ? "Fatura paga." : "Pagamento parcial registrado.");
      onDone();
    }
  };
  return (
    <form className="card stack" onSubmit={onSubmit} noValidate>
      <h2>Pagar fatura</h2>
      <p className="small muted">O pagamento sai da conta escolhida. As compras já foram contadas como gasto no dia em que foram feitas; o pagamento não é contado de novo.</p>
      <FormError error={submit.error} />
      <MoneyInput label="Valor pago" cents={amount} onChange={setAmount} error={submit.fields.amount_cents}
        hint={`Falta ${formatCents(inv.remaining_cents)}. Pode pagar só uma parte.`} />
      <Select label="Conta usada" value={account} onChange={setAccountId} options={accounts.options} error={submit.fields.account_id} />
      <DateInput label="Data do pagamento" value={date} onChange={setDate} max={todayInSaoPaulo()} />
      <SubmitButton busy={submit.busy} online={online}>Registrar pagamento</SubmitButton>
    </form>
  );
}

function Renegotiate({ inv, onDone }: { inv: InvoiceDetail; onDone: () => void }) {
  const { online, flash } = useShell();
  const submit = useSubmit();
  const [financed, setFinanced] = useState<number | null>(inv.remaining_cents);
  const [count, setCount] = useState("");
  const [installment, setInstallment] = useState<number | null>(null);
  const n = Number(count) || 0;
  const total = n && installment ? n * installment : null;
  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const ok = await submit.run((key) =>
      api.create(`/cartoes/${inv.card.id}/faturas/${inv.due_date}/renegociar`, {
        financed_cents: financed, installments_count: n, installment_cents: installment,
      }, key),
    );
    if (ok) {
      flash("Parcelamento registrado. Acompanhe em Dívidas; as parcelas vêm nas próximas faturas.");
      onDone();
    }
  };
  return (
    <details className="card more">
      <summary>Parcelar esta fatura com o banco</summary>
      <form className="stack" style={{ marginTop: 8 }} onSubmit={onSubmit} noValidate>
        <p className="small muted">
          Use quando o banco parcelar o saldo da fatura. O valor parcelado sai desta fatura e as parcelas do acordo entram nas próximas,
          sem contar a dívida duas vezes.
        </p>
        <FormError error={submit.error} />
        <MoneyInput label="Valor parcelado" cents={financed} onChange={setFinanced} error={submit.fields.financed_cents} />
        <NumberInput label="Número de parcelas" value={count} onChange={setCount} max={72} error={submit.fields.installments_count} />
        <MoneyInput label="Valor de cada parcela (como está no acordo)" cents={installment} onChange={setInstallment}
          error={submit.fields.installment_cents} />
        {total !== null && financed !== null ? (
          <p>Total do acordo: <strong>{formatCents(total)}</strong>{total > financed ? ` (juros de ${formatCents(total - financed)})` : ""}.</p>
        ) : null}
        <SubmitButton busy={submit.busy} online={online}>Registrar parcelamento</SubmitButton>
      </form>
    </details>
  );
}

function Detail({ id, due }: { id: string; due: string }) {
  const inv = useApi<InvoiceDetail>(`/cartoes/${id}/faturas/${due}`);
  if (inv.state === "loading") return <Loading />;
  if (inv.state === "error") return <ErrorBox message={inv.message} onRetry={inv.reload} />;
  const i = inv.data;
  const canPay = i.remaining_cents > 0;
  return (
    <div className="stack-lg">
      <BackLink href={`/cartoes/detalhe/?id=${id}`}>{i.card.name}</BackLink>
      <PageHeader title={<>Fatura de <DateText iso={i.due_date} /></>}
        subtitle={<>Fecha <DateText iso={i.closing_date} /> · vence <DateText iso={i.due_date} /></>} />
      <div className="card stack">
        <Situation value={i.status} />
        <div className="grid-2">
          <Stat size="md" label="Total da fatura" cents={i.total_cents} />
          <Stat size="md" label="Falta pagar" cents={i.remaining_cents} />
        </div>
        <table className="data">
          <tbody>
            <tr><td>Compras, parcelas e tarifas</td><td className="num"><Money cents={i.charges_cents} /></td></tr>
            {i.credits_cents ? <tr><td>Estornos e créditos</td><td className="num"><Money cents={-i.credits_cents} /></td></tr> : null}
            {i.carried_credit_cents ? <tr><td>Crédito da fatura anterior</td><td className="num"><Money cents={-i.carried_credit_cents} /></td></tr> : null}
            {i.payments_cents ? <tr><td>Já pago</td><td className="num"><Money cents={-i.payments_cents} /></td></tr> : null}
          </tbody>
        </table>
      </div>
      {canPay ? <PayInvoice key={i.remaining_cents} inv={i} onDone={inv.reload} /> : null}
      <section className="stack">
        <h2>O que está nesta fatura</h2>
        {i.items.length === 0 ? <p className="muted">Nenhuma compra nesta fatura.</p> : (
          <ul className="list">
            {i.items.map((it) => (
              <li key={it.id}>
                <Link className="list-row" href={`/cartoes/compra/?id=${it.purchase_id}`}>
                  <span className="main">
                    <span className="title">{it.description}</span>
                    <span className="sub">
                      <DateText iso={it.purchase_date} />
                      {it.installments_count > 1 ? ` · parcela ${it.number} de ${it.installments_count}` : ""}
                      {it.status === "cancelada" ? " · cancelada" : ""}
                    </span>
                  </span>
                  <Money cents={it.amount_cents} className="amount" />
                </Link>
              </li>
            ))}
          </ul>
        )}
        {i.credits.length > 0 ? (
          <ul className="list" aria-label="Créditos">
            {i.credits.map((c) => (
              <li key={c.id} className="list-row">
                <span className="main"><span className="title">{c.description}</span><span className="sub"><DateText iso={c.credit_date} /></span></span>
                <Money cents={-c.amount_cents} className="amount" />
              </li>
            ))}
          </ul>
        ) : null}
      </section>
      {i.payments.length > 0 ? (
        <section className="stack">
          <h2>Pagamentos</h2>
          <ul className="list">
            {i.payments.map((p) => (
              <li key={p.id} className="list-row">
                <span className="main"><span className="title"><DateText iso={p.tx_date} /> · {p.account_name}</span>
                  {p.status === "cancelado" ? <span className="sub">Cancelado</span> : null}</span>
                <Money cents={p.amount_cents} className="amount" />
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {canPay ? <Renegotiate inv={i} onDone={inv.reload} /> : null}
    </div>
  );
}

function Inner() {
  const p = useSearchParams();
  const id = p.get("id");
  const due = p.get("venc");
  if (!id || !due) return <ErrorBox message="Fatura não informada." />;
  return <Detail id={id} due={due} />;
}

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <Inner />
    </Suspense>
  );
}
