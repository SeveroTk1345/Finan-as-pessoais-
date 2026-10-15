"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, Suspense, useState } from "react";

import { useShell } from "@/components/Shell";
import {
  BackLink, Badge, ConfirmButton, DateInput, DateText, ErrorBox, FormError, Loading, Money, MoneyInput, NumberInput, PageHeader,
  Progress, Segmented, Select, Stat, SubmitButton, useScrollToError,
} from "@/components/ui";
import { api } from "@/lib/api";
import { todayInSaoPaulo } from "@/lib/dates";
import { formatCents } from "@/lib/format";
import { useApi, useSubmit } from "@/lib/hooks";
import { DEBT_KINDS, useAccounts } from "@/lib/options";
import type { Debt } from "@/lib/types";


function PayDebt({ d, onDone }: { d: Debt; onDone: () => void }) {
  const { online, flash } = useShell();
  const accounts = useAccounts();
  const submit = useSubmit();
  useScrollToError(submit.error);
  const [type, setType] = useState<"parcela" | "amortizacao" | "quitacao">("parcela");
  const [amount, setAmount] = useState<number | null>(d.installment_amount_cents ? Math.min(d.installment_amount_cents, d.balance_cents) : null);
  const [interest, setInterest] = useState<number | null>(null);
  const [accountId, setAccountId] = useState("");
  const [date, setDate] = useState(todayInSaoPaulo());
  const account = accountId || accounts.options[0]?.value || "";
  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (amount === null) return submit.setError("Informe o valor pago.");
    const ok = await submit.run((key) =>
      api.create(`/dividas/${d.id}/pagamentos`, { account_id: account, amount_cents: amount, interest_cents: interest, tx_date: date, payment_type: type }, key),
    );
    if (ok) {
      flash("Pagamento registrado.");
      onDone();
    }
  };
  return (
    <form className="card stack" onSubmit={onSubmit} noValidate>
      <h2>Registrar pagamento</h2>
      <FormError error={submit.error} />
      <Segmented label="Tipo de pagamento" value={type} onChange={(t) => { setType(t); if (t === "quitacao") setAmount(d.balance_cents); }}
        options={[{ value: "parcela", label: "Parcela" }, { value: "amortizacao", label: "Valor extra" }, { value: "quitacao", label: "Quitar tudo" }]} />
      <MoneyInput label="Valor pago" cents={amount} onChange={setAmount} error={submit.fields.amount_cents} />
      <MoneyInput label="Quanto desse valor foi juros (opcional)" cents={interest} onChange={setInterest} allowZero
        error={submit.fields.interest_cents} hint="Se não souber, deixe em branco: o saldo fica marcado como estimado." />
      <Select label="Conta usada" value={account} onChange={setAccountId} options={accounts.options} error={submit.fields.account_id} />
      <DateInput label="Data" value={date} onChange={setDate} max={todayInSaoPaulo()} />
      <SubmitButton busy={submit.busy} online={online}>Registrar pagamento</SubmitButton>
    </form>
  );
}

function ChargeForm({ d, onDone }: { d: Debt; onDone: () => void }) {
  const { online, flash } = useShell();
  const submit = useSubmit();
  const [kind, setKind] = useState<"encargo" | "desconto">("encargo");
  const [amount, setAmount] = useState<number | null>(null);
  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const ok = await submit.run((key) => api.create(`/dividas/${d.id}/eventos`, { kind, amount_cents: amount }, key));
    if (ok) {
      flash(kind === "encargo" ? "Juros ou multa registrados." : "Desconto registrado.");
      setAmount(null);
      onDone();
    }
  };
  return (
    <details className="card more">
      <summary>Juros, multa ou desconto</summary>
      <form className="stack" style={{ marginTop: 8 }} onSubmit={onSubmit} noValidate>
        <FormError error={submit.error} />
        <Segmented label="O que aconteceu" value={kind} onChange={setKind}
          options={[{ value: "encargo", label: "Juros ou multa (aumenta)" }, { value: "desconto", label: "Desconto (diminui)" }]} />
        <MoneyInput label="Valor" cents={amount} onChange={setAmount} error={submit.fields.amount_cents} />
        <SubmitButton busy={submit.busy} online={online}>Registrar</SubmitButton>
      </form>
    </details>
  );
}

function Renegotiate({ d }: { d: Debt }) {
  const router = useRouter();
  const { online, flash } = useShell();
  const submit = useSubmit();
  const [balance, setBalance] = useState<number | null>(null);
  const [count, setCount] = useState("");
  const [installment, setInstallment] = useState<number | null>(null);
  const [first, setFirst] = useState("");
  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (balance === null) return submit.setError("Informe o novo saldo combinado.");
    const res = await submit.run((key) =>
      api.create<{ new: { id: string } }>(`/dividas/${d.id}/renegociar`, {
        new_balance_cents: balance, installments_total: count ? Number(count) : null, installment_amount_cents: installment,
        first_due_date: first || null,
      }, key),
    );
    if (res) {
      flash("Renegociação registrada. A dívida antiga fica no histórico.");
      router.push(`/dividas/detalhe/?id=${res.new.id}`);
    }
  };
  return (
    <details className="card more">
      <summary>Renegociar esta dívida</summary>
      <form className="stack" style={{ marginTop: 8 }} onSubmit={onSubmit} noValidate>
        <p className="small muted">A dívida atual é encerrada como “renegociada” (sem sair dinheiro) e uma nova é criada com as condições do acordo.</p>
        <FormError error={submit.error} />
        <MoneyInput label="Novo saldo combinado" cents={balance} onChange={setBalance} error={submit.fields.new_balance_cents} />
        <NumberInput label="Número de parcelas (opcional)" value={count} onChange={setCount} max={600} />
        <MoneyInput label="Valor de cada parcela (opcional)" cents={installment} onChange={setInstallment} />
        <DateInput label="Primeiro vencimento (opcional)" value={first} onChange={setFirst} />
        <SubmitButton busy={submit.busy} online={online}>Registrar renegociação</SubmitButton>
      </form>
    </details>
  );
}

function Detail({ id }: { id: string }) {
  const router = useRouter();
  const { online, flash } = useShell();
  const debt = useApi<Debt>(`/dividas/${id}`);
  const [error, setError] = useState<string | null>(null);
  if (debt.state === "loading") return <Loading />;
  if (debt.state === "error") return <ErrorBox message={debt.message} onRetry={debt.reload} />;
  const d = debt.data;
  const active = d.status === "ativa";
  const percent = d.installments_total ? Math.floor((d.installments_paid * 100) / d.installments_total) : null;
  return (
    <div className="stack-lg">
      <BackLink href="/dividas/">Dívidas</BackLink>
      <PageHeader title={d.creditor} subtitle={DEBT_KINDS[d.kind] ?? d.kind} />
      <div className="card stack">
        {d.status === "quitada" ? <Badge tone="pos">Dívida quitada</Badge> : null}
        {d.status === "renegociada" ? <Badge tone="warn">Renegociada: veja a nova dívida</Badge> : null}
        <Stat label="Falta pagar" cents={d.balance_cents}
          help={d.balance_estimated ? "Valor estimado: alguns pagamentos não informaram quanto foi de juros." : "Conforme os dados registrados."} />
        {d.installments_total ? (
          <>
            <p><strong>Você já pagou {d.installments_paid} de {d.installments_total} parcelas.</strong></p>
            {percent !== null ? <Progress percent={percent} label="Parcelas pagas" /> : null}
          </>
        ) : null}
        {d.next_due_date ? (
          <p>
            Próxima parcela: <DateText iso={d.next_due_date} />
            {d.installment_amount_cents ? <> · {formatCents(Math.min(d.installment_amount_cents, d.balance_cents))}</> : null}
            {d.overdue ? <> <Badge tone="neg">Atrasada</Badge></> : null}
          </p>
        ) : null}
        <p className="small muted">
          {d.interest_rate ? `Taxa informada: ${d.interest_rate.replace(".", ",")}% ao ${d.rate_period === "anual" ? "ano" : "mês"}.` : "Taxa de juros não informada."}
          {" "}Total já pago: {formatCents(d.total_paid_cents)}.
        </p>
      </div>
      <FormError error={error} />
      {d.is_card_channel ? (
        <p className="notice">
          Este parcelamento é cobrado nas faturas do cartão. Pague pela fatura em <Link href="/cartoes/">Cartões</Link>: assim nada é contado duas vezes.
        </p>
      ) : active ? (
        <>
          <PayDebt key={d.balance_cents} d={d} onDone={debt.reload} />
          <ChargeForm d={d} onDone={debt.reload} />
          <Renegotiate d={d} />
        </>
      ) : null}

      {d.payments && d.payments.length > 0 ? (
        <section className="stack">
          <h2>Pagamentos</h2>
          <ul className="list">
            {d.payments.map((p) => (
              <li key={p.id} className="list-row">
                <span className="main">
                  <span className="title"><DateText iso={p.tx_date} /> · {p.debt_payment_type === "parcela" ? "Parcela" : p.debt_payment_type === "quitacao" ? "Quitação" : "Valor extra"}</span>
                  <span className="sub">{p.account_name}{p.debt_interest_cents !== null ? ` · juros ${formatCents(p.debt_interest_cents)}` : ""}{p.status === "cancelado" ? " · cancelado" : ""}</span>
                </span>
                <Money cents={p.amount_cents} className="amount" />
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {d.events && d.events.length > 0 ? (
        <section className="stack">
          <h2>Juros, multas e descontos</h2>
          <ul className="list">
            {d.events.map((e) => (
              <li key={e.id} className="list-row">
                <span className="main"><span className="title">{e.description}</span><span className="sub"><DateText iso={e.event_date} /></span></span>
                <Money cents={e.kind === "encargo" ? e.amount_cents : -e.amount_cents} className="amount" />
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {active && !d.is_card_channel && (!d.payments || d.payments.filter((p) => p.status === "ativo").length === 0) ? (
        <ConfirmButton label="Cancelar dívida (cadastrada por engano)" tone="secondary" title="Cancelar esta dívida?"
          message={<p>Use só se a dívida foi cadastrada por engano. Ela fica no histórico como cancelada.</p>}
          confirmLabel="Cancelar dívida" disabled={!online}
          onConfirm={async () => {
            try {
              await api.post(`/dividas/${id}/cancelar`);
              flash("Dívida cancelada.");
              router.push("/dividas/");
            } catch (e) {
              setError(e instanceof Error ? e.message : "Erro.");
            }
          }} />
      ) : null}
    </div>
  );
}

function Inner() {
  const id = useSearchParams().get("id");
  if (!id) return <ErrorBox message="Dívida não informada." />;
  return <Detail id={id} />;
}

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <Inner />
    </Suspense>
  );
}
