"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { useShell } from "@/components/Shell";
import { BackLink, Checkbox, DateInput, FormError, MoneyInput, PageHeader, Segmented, Select, SubmitButton, TextInput, useScrollToError } from "@/components/ui";
import { api } from "@/lib/api";
import { todayInSaoPaulo } from "@/lib/dates";
import { useSubmit } from "@/lib/hooks";
import { ACCOUNT_KINDS } from "@/lib/options";

export default function NewAccountPage() {
  const router = useRouter();
  const { online, flash } = useShell();
  const submit = useSubmit();
  useScrollToError(submit.error);
  const [name, setName] = useState("");
  const [institution, setInstitution] = useState("");
  const [kind, setKind] = useState("corrente");
  const [balance, setBalance] = useState<number | null>(null);
  const [negative, setNegative] = useState<"positivo" | "negativo">("positivo");
  const [date, setDate] = useState(todayInSaoPaulo());
  const [daily, setDaily] = useState(true);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const cents = (balance ?? 0) * (negative === "negativo" ? -1 : 1);
    const ok = await submit.run((key) =>
      api.create("/contas", {
        name, institution: institution || null, kind, initial_balance_cents: cents,
        initial_balance_date: date, daily_use: kind === "outra" ? daily : true,
      }, key),
    );
    if (ok) {
      flash("Conta cadastrada.");
      router.push("/contas/");
    }
  };
  const f = submit.fields;
  return (
    <form className="stack-lg" onSubmit={onSubmit} noValidate>
      <BackLink href="/contas/">Contas</BackLink>
      <PageHeader title="Nova conta" />
      <FormError error={submit.error} />
      <div className="stack">
        <TextInput label="Nome da conta" value={name} onChange={setName} maxLength={80} error={f.name}
          hint="Ex.: Conta do banco, Poupança, Carteira" />
        <Select label="Tipo" value={kind} onChange={setKind}
          options={Object.entries(ACCOUNT_KINDS).map(([value, label]) => ({ value, label }))} error={f.kind} />
        <TextInput label="Banco ou instituição (opcional)" value={institution} onChange={setInstitution} maxLength={80} />
        <MoneyInput label="Quanto há nesta conta" cents={balance} onChange={setBalance} allowZero error={f.initial_balance_cents} />
        <Segmented label="O saldo está" value={negative} onChange={setNegative}
          options={[{ value: "positivo", label: "Positivo" }, { value: "negativo", label: "Negativo (no vermelho)" }]} />
        <DateInput label="Saldo do dia" value={date} onChange={setDate} max={todayInSaoPaulo()} error={f.initial_balance_date}
          hint="Lançamentos a partir desta data alteram o saldo." />
        {kind === "outra" ? (
          <Checkbox label="Contar no dinheiro disponível para o dia a dia" checked={daily} onChange={setDaily} />
        ) : null}
      </div>
      <SubmitButton busy={submit.busy} online={online}>Salvar conta</SubmitButton>
    </form>
  );
}
