"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, Suspense, useState } from "react";

import { useShell } from "@/components/Shell";
import {
  BackLink, ConfirmButton, DateInput, DateText, ErrorBox, FormError, Loading, Money, MoneyInput, PageHeader, Select, Situation, Stat,
  SubmitButton, useScrollToError,
} from "@/components/ui";
import { api } from "@/lib/api";
import { todayInSaoPaulo } from "@/lib/dates";
import { formatCents } from "@/lib/format";
import { useApi, useSubmit } from "@/lib/hooks";
import { useAccounts } from "@/lib/options";
import { billTitle, type Bill } from "@/lib/types";

function PayForm({ bill, onDone }: { bill: Bill; onDone: () => void }) {
  const { online, flash } = useShell();
  const accounts = useAccounts();
  const submit = useSubmit();
  useScrollToError(submit.error);
  const receiving = bill.kind === "receber";
  const [amount, setAmount] = useState<number | null>(bill.remaining_cents);
  const [accountId, setAccountId] = useState(bill.account_id ?? "");
  const [date, setDate] = useState(todayInSaoPaulo());
  const account = accountId || accounts.options[0]?.value || "";
  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const ok = await submit.run((key) =>
      api.create(`/contas-a-pagar/${bill.id}/pagar`, { amount_cents: amount, account_id: account, tx_date: date }, key),
    );
    if (ok) {
      flash(receiving ? "Recebimento registrado." : amount === bill.remaining_cents ? "Pagamento registrado. Conta paga." : "Pagamento parcial registrado.");
      onDone();
    }
  };
  return (
    <form className="card stack" onSubmit={onSubmit} noValidate>
      <h2>{receiving ? "Registrar recebimento" : "Registrar pagamento"}</h2>
      <FormError error={submit.error} />
      <MoneyInput label={receiving ? "Valor recebido" : "Valor pago"} cents={amount} onChange={setAmount}
        error={submit.fields.amount_cents} hint={`Falta ${formatCents(bill.remaining_cents)}. Pode registrar só uma parte.`} />
      <Select label={receiving ? "Conta onde caiu" : "Conta usada"} value={account} onChange={setAccountId} options={accounts.options}
        error={submit.fields.account_id} />
      <DateInput label="Data" value={date} onChange={setDate} max={todayInSaoPaulo()} error={submit.fields.tx_date} />
      <SubmitButton busy={submit.busy} online={online}>{receiving ? "Registrar recebimento" : "Registrar pagamento"}</SubmitButton>
    </form>
  );
}

function Detail({ id }: { id: string }) {
  const router = useRouter();
  const { online, flash } = useShell();
  const bill = useApi<Bill>(`/contas-a-pagar/${id}`);
  const [error, setError] = useState<string | null>(null);
  if (bill.state === "loading") return <Loading />;
  if (bill.state === "error") return <ErrorBox message={bill.message} onRetry={bill.reload} />;
  const b = bill.data;
  const receiving = b.kind === "receber";
  const open = b.situation !== "paga" && b.situation !== "cancelada";
  const cancel = async () => {
    try {
      await api.post(`/contas-a-pagar/${id}/cancelar`);
      flash("Conta cancelada.");
      router.push("/a-pagar/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro.");
    }
  };
  const cancelPlan = async () => {
    try {
      const r = await api.post<{ cancelled: number }>(`/parcelamentos/${b.installment_group}/cancelar`);
      flash(r.cancelled === 1 ? "1 parcela cancelada." : `${r.cancelled} parcelas canceladas.`);
      router.push("/a-pagar/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro.");
    }
  };
  return (
    <div className="stack-lg">
      <BackLink href="/a-pagar/">Contas a pagar</BackLink>
      <PageHeader title={billTitle(b)} subtitle={<>Vence <DateText iso={b.due_date} />{b.category_name ? ` · ${b.category_name}` : ""}</>} />
      <div className="card stack">
        <div className="between"><Situation value={b.situation} receiving={receiving} /></div>
        <div className="grid-2">
          <Stat size="md" label="Valor" cents={b.amount_cents} />
          <Stat size="md" label={receiving ? "Falta receber" : "Falta pagar"} cents={b.remaining_cents} />
        </div>
        {b.situation === "vencida" ? (
          <p className="neg">Esta conta venceu e continua pendente até ser paga ou cancelada.</p>
        ) : null}
      </div>
      <FormError error={error} />
      {open ? <PayForm key={b.remaining_cents} bill={b} onDone={bill.reload} /> : null}
      {b.payments && b.payments.length > 0 ? (
        <section className="stack">
          <h2>{receiving ? "Recebimentos" : "Pagamentos"}</h2>
          <ul className="list">
            {b.payments.map((p) => (
              <li key={p.id} className="list-row">
                <span className="main">
                  <span className="title"><DateText iso={p.tx_date} /> · {p.account_name}</span>
                  {p.status === "cancelado" ? <span className="sub">Cancelado</span> : null}
                </span>
                <Money cents={p.amount_cents} className="amount" />
              </li>
            ))}
          </ul>
          <p className="small muted">Para desfazer um pagamento, abra-o em Receitas e despesas e cancele.</p>
        </section>
      ) : null}
      {b.installment_group && open ? (
        <ConfirmButton label="Cancelar as parcelas que faltam" title="Cancelar as parcelas que faltam?" tone="secondary"
          message={<p>Todas as parcelas ainda não pagas desta compra deixam de aparecer. As já pagas continuam registradas.
            Use se a compra foi desfeita ou quitada de outro jeito.</p>}
          confirmLabel="Sim, cancelar as que faltam" onConfirm={cancelPlan} disabled={!online} />
      ) : null}
      {b.situation !== "cancelada" && b.situation !== "paga" ? (
        <ConfirmButton label="Cancelar esta conta" title="Cancelar esta conta?"
          message={<p>Ela deixa de aparecer como pendente. {b.paid_cents > 0 ? "Os pagamentos já feitos continuam registrados." : ""}</p>}
          confirmLabel="Sim, cancelar" onConfirm={cancel} disabled={!online} />
      ) : null}
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
