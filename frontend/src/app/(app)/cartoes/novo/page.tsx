"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { useShell } from "@/components/Shell";
import { BackLink, Checkbox, FormError, MoneyInput, NumberInput, PageHeader, SubmitButton, TextInput, useScrollToError } from "@/components/ui";
import { api } from "@/lib/api";
import { useSubmit } from "@/lib/hooks";

export default function NewCardPage() {
  const router = useRouter();
  const { online, flash } = useShell();
  const submit = useSubmit();
  useScrollToError(submit.error);
  const [name, setName] = useState("");
  const [institution, setInstitution] = useState("");
  const [limit, setLimit] = useState<number | null>(null);
  const [closing, setClosing] = useState("");
  const [due, setDue] = useState("");
  const [goesNext, setGoesNext] = useState(true);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const ok = await submit.run((key) =>
      api.create("/cartoes", {
        name, institution: institution || null, limit_cents: limit ?? 0,
        closing_day: Number(closing), due_day: Number(due), closing_day_goes_next: goesNext,
      }, key),
    );
    if (ok) {
      flash("Cartão cadastrado.");
      router.push("/cartoes/");
    }
  };
  const f = submit.fields;
  return (
    <form className="stack-lg" onSubmit={onSubmit} noValidate>
      <BackLink href="/cartoes/">Cartões</BackLink>
      <PageHeader title="Novo cartão" />
      <FormError error={submit.error} />
      <div className="stack">
        <TextInput label="Nome do cartão" value={name} onChange={setName} maxLength={60} error={f.name} hint="Ex.: Cartão Nubank, Visa do banco" />
        <TextInput label="Banco (opcional)" value={institution} onChange={setInstitution} maxLength={60} />
        <MoneyInput label="Limite total" cents={limit} onChange={setLimit} allowZero error={f.limit_cents} />
        <NumberInput label="Dia em que a fatura fecha" value={closing} onChange={setClosing} max={31} error={f.closing_day}
          hint="Está na fatura como “melhor dia de compra” ou “fechamento”." />
        <NumberInput label="Dia do vencimento" value={due} onChange={setDue} max={31} error={f.due_day} />
        <Checkbox label="Compras no dia do fechamento entram na fatura seguinte" checked={goesNext} onChange={setGoesNext} />
      </div>
      <SubmitButton busy={submit.busy} online={online}>Salvar cartão</SubmitButton>
    </form>
  );
}
