"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { useShell } from "@/components/Shell";
import {
  BackLink, Checkbox, DateInput, Field, FormError, MoneyInput, NumberInput, PageHeader, Select, SubmitButton, TextInput, useScrollToError,
} from "@/components/ui";
import { api } from "@/lib/api";
import { todayInSaoPaulo } from "@/lib/dates";
import { useSubmit } from "@/lib/hooks";
import { useAccounts } from "@/lib/options";

const KINDS = [
  { value: "emprestimo", label: "Empréstimo" },
  { value: "financiamento", label: "Financiamento" },
  { value: "parcelamento", label: "Compra parcelada (carnê, boleto)" },
  { value: "outra", label: "Outra dívida" },
];

export default function NewDebtPage() {
  const router = useRouter();
  const { online, flash } = useShell();
  const accounts = useAccounts();
  const submit = useSubmit();
  useScrollToError(submit.error);
  const [creditor, setCreditor] = useState("");
  const [kind, setKind] = useState("emprestimo");
  const [original, setOriginal] = useState<number | null>(null);
  const [current, setCurrent] = useState<number | null>(null);
  const [rate, setRate] = useState("");
  const [period, setPeriod] = useState("mensal");
  const [total, setTotal] = useState("");
  const [paidBefore, setPaidBefore] = useState("");
  const [installment, setInstallment] = useState<number | null>(null);
  const [firstDue, setFirstDue] = useState("");
  const [received, setReceived] = useState(false);
  const [accountId, setAccountId] = useState("");

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (original === null) return submit.setError("Informe o valor original da dívida.");
    const rateValue = rate.trim().replace(",", ".");
    const ok = await submit.run((key) =>
      api.create("/dividas", {
        creditor, kind, original_amount_cents: original, current_balance_cents: current ?? original,
        balance_date: todayInSaoPaulo(),
        interest_rate: rateValue ? rateValue : null, rate_period: rateValue ? period : null,
        installments_total: total ? Number(total) : null, installments_paid_before: paidBefore ? Number(paidBefore) : 0,
        installment_amount_cents: installment, first_due_date: firstDue || null,
        disbursement_account_id: received ? accountId || accounts.options[0]?.value : null,
      }, key),
    );
    if (ok) {
      flash("Dívida cadastrada.");
      router.push("/dividas/");
    }
  };
  const f = submit.fields;
  return (
    <form className="stack-lg" onSubmit={onSubmit} noValidate>
      <BackLink href="/dividas/">Dívidas</BackLink>
      <PageHeader title="Nova dívida" subtitle="Preencha o que souber. Campos em branco não são inventados." />
      <FormError error={submit.error} />
      <div className="stack">
        <TextInput label="Para quem você deve?" value={creditor} onChange={setCreditor} maxLength={80} error={f.creditor}
          hint="Ex.: Banco, loja, financeira" />
        <Select label="Tipo" value={kind} onChange={setKind} options={KINDS} />
        <MoneyInput label="Valor original (quanto pegou ou comprou)" cents={original} onChange={setOriginal} error={f.original_amount_cents} />
        <MoneyInput label="Quanto falta pagar hoje" cents={current} onChange={setCurrent} allowZero error={f.current_balance_cents}
          hint="Se não souber, deixe em branco: usamos o valor original." />
        <MoneyInput label="Valor de cada parcela (opcional)" cents={installment} onChange={setInstallment} error={f.installment_amount_cents} />
        <div className="grid-2">
          <NumberInput label="Total de parcelas (opcional)" value={total} onChange={setTotal} max={600} error={f.installments_total} />
          <NumberInput label="Parcelas já pagas" value={paidBefore} onChange={setPaidBefore} max={600} error={f.installments_paid_before} />
        </div>
        <DateInput label="Vencimento da próxima parcela (opcional)" value={firstDue} onChange={setFirstDue} error={f.first_due_date} />
        <Field label="Taxa de juros (opcional)" hint="Ex.: 2,5. Se não souber, deixe em branco." error={f.interest_rate}>
          {(id, d) => (
            <input id={id} className="input" inputMode="decimal" value={rate} aria-describedby={d}
              onChange={(e) => setRate(e.target.value.replace(/[^0-9,]/g, "").slice(0, 8))} />
          )}
        </Field>
        {rate ? <Select label="A taxa é" value={period} onChange={setPeriod} options={[{ value: "mensal", label: "% ao mês" }, { value: "anual", label: "% ao ano" }]} /> : null}
        <Checkbox label="O dinheiro do empréstimo entrou em uma das minhas contas" checked={received} onChange={setReceived} />
        {received ? (
          <Select label="Conta onde entrou" value={accountId || accounts.options[0]?.value || ""} onChange={setAccountId} options={accounts.options}
            hint="Entra como empréstimo, não como receita." />
        ) : null}
      </div>
      <SubmitButton busy={submit.busy} online={online}>Salvar dívida</SubmitButton>
    </form>
  );
}
