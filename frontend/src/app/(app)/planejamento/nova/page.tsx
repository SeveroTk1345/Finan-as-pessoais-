"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { useShell } from "@/components/Shell";
import { BackLink, DateInput, Field, FormError, MoneyInput, PageHeader, Select, SubmitButton, TextInput, useScrollToError } from "@/components/ui";
import { api } from "@/lib/api";
import { useSubmit } from "@/lib/hooks";

const KINDS = [
  { value: "reserva_emergencia", label: "Reserva de emergência" },
  { value: "viagem", label: "Viagem" },
  { value: "carro", label: "Carro" },
  { value: "imovel", label: "Imóvel" },
  { value: "quitar_dividas", label: "Quitar dívidas" },
  { value: "outro", label: "Outro objetivo" },
];

export default function NewGoalPage() {
  const router = useRouter();
  const { online, flash } = useShell();
  const submit = useSubmit();
  useScrollToError(submit.error);
  const [kind, setKind] = useState("reserva_emergencia");
  const [name, setName] = useState("");
  const [target, setTarget] = useState<number | null>(null);
  const [initial, setInitial] = useState<number | null>(null);
  const [monthly, setMonthly] = useState<number | null>(null);
  const [date, setDate] = useState("");
  const [rate, setRate] = useState("");

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (target === null) return submit.setError("Informe quanto você quer juntar.");
    const ok = await submit.run((key) =>
      api.create("/metas", {
        name: name || KINDS.find((k) => k.value === kind)?.label, kind, target_cents: target, initial_amount_cents: initial,
        planned_monthly_cents: monthly, target_date: date || null, assumed_annual_rate: rate ? rate.replace(",", ".") : null,
      }, key),
    );
    if (ok) {
      flash("Meta criada.");
      router.push("/planejamento/");
    }
  };
  return (
    <form className="stack-lg" onSubmit={onSubmit} noValidate>
      <BackLink href="/planejamento/">Planejamento</BackLink>
      <PageHeader title="Nova meta" />
      <FormError error={submit.error} />
      <div className="stack">
        <Select label="Objetivo" value={kind} onChange={setKind} options={KINDS} />
        <TextInput label="Nome (opcional)" value={name} onChange={setName} maxLength={80} hint="Ex.: Viagem para a praia" />
        <MoneyInput label="Quanto quer juntar" cents={target} onChange={setTarget} error={submit.fields.target_cents} />
        <MoneyInput label="Quanto já tem guardado para isso (opcional)" cents={initial} onChange={setInitial} allowZero />
        <MoneyInput label="Quanto pretende guardar por mês (opcional)" cents={monthly} onChange={setMonthly} />
        <DateInput label="Até quando (opcional)" value={date} onChange={setDate} />
        <Field label="Rendimento esperado ao ano, em % (opcional)" hint="Usado só para estimar. Rendimento não é garantido.">
          {(id, d) => <input id={id} className="input" inputMode="decimal" value={rate} aria-describedby={d}
            onChange={(e) => setRate(e.target.value.replace(/[^0-9,]/g, "").slice(0, 6))} />}
        </Field>
      </div>
      <SubmitButton busy={submit.busy} online={online}>Criar meta</SubmitButton>
    </form>
  );
}
