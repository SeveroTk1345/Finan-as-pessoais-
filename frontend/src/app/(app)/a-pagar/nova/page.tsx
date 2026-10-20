"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, Suspense, useState } from "react";

import { useShell } from "@/components/Shell";
import {
  CategoryPicker,
  BackLink, Checkbox, DateInput, FormError, Loading, MoneyInput, PageHeader, Segmented, Select, SubmitButton, TextInput, useScrollToError,
} from "@/components/ui";
import { api } from "@/lib/api";
import { todayInSaoPaulo } from "@/lib/dates";
import { useSubmit } from "@/lib/hooks";
import { CATEGORY_HINTS, NATURES, useAccounts, useCategories } from "@/lib/options";

function NewBill() {
  const params = useSearchParams();
  const router = useRouter();
  const { online, flash } = useShell();
  const [kind, setKind] = useState<"pagar" | "receber">(params.get("tipo") === "receber" ? "receber" : "pagar");
  const accounts = useAccounts();
  const categories = useCategories(kind === "receber" ? "receita" : "despesa");
  const submit = useSubmit();
  useScrollToError(submit.error);
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState<number | null>(null);
  const [due, setDue] = useState(todayInSaoPaulo());
  const [repeat, setRepeat] = useState<"nao" | "mensal" | "semanal" | "anual">("nao");
  const [categoryId, setCategoryId] = useState("");
  const [accountId, setAccountId] = useState("");
  const [nature, setNature] = useState("");
  const [main, setMain] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (amount === null) return submit.setError("Informe o valor.");
    const common = {
      kind, description, amount_cents: amount, category_id: categoryId || null, account_id: accountId || null,
      expense_nature: kind === "pagar" && nature ? nature : null, is_main_income: kind === "receber" && main,
    };
    const ok = await submit.run((key) =>
      repeat === "nao"
        ? api.create("/contas-a-pagar", { ...common, due_date: due }, key)
        : api.create("/recorrencias", { ...common, frequency: repeat, anchor_date: due }, key),
    );
    if (ok) {
      flash(repeat === "nao" ? "Salvo." : "Salvo. As próximas ocorrências aparecem automaticamente.");
      router.push("/a-pagar/");
    }
  };
  const f = submit.fields;
  return (
    <form className="stack-lg" onSubmit={onSubmit} noValidate>
      <BackLink href="/a-pagar/">Contas a pagar</BackLink>
      <PageHeader title={kind === "pagar" ? "Nova conta a pagar" : "Nova receita prevista"} />
      <Segmented label="Tipo" value={kind} onChange={(k) => { setKind(k); setCategoryId(""); }}
        options={[{ value: "pagar", label: "Vou pagar" }, { value: "receber", label: "Vou receber" }]} />
      <FormError error={submit.error} />
      <div className="stack">
        <TextInput label="Descrição" value={description} onChange={setDescription} error={f.description}
          hint={kind === "pagar" ? "Ex.: Aluguel, Conta de luz, Plano de saúde" : "Ex.: Salário, Aposentadoria"} />
        <MoneyInput label="Valor" cents={amount} onChange={setAmount} error={f.amount_cents} />
        <DateInput label={repeat === "nao" ? "Vencimento" : "Primeiro vencimento"} value={due} onChange={setDue}
          error={f.due_date ?? f.anchor_date} />
        <Select label="Repetir" value={repeat} onChange={(v) => setRepeat(v as typeof repeat)} options={[
          { value: "nao", label: "Não repete" }, { value: "mensal", label: "Todo mês" },
          { value: "semanal", label: "Toda semana" }, { value: "anual", label: "Todo ano" },
        ]} hint="Contas do dia 31 caem no último dia dos meses mais curtos." />
        <CategoryPicker label="Categoria" value={categoryId} onChange={setCategoryId} options={categories.options} hints={CATEGORY_HINTS} />
        <Select label={kind === "pagar" ? "Conta usada para pagar (opcional)" : "Conta onde vai cair (opcional)"} value={accountId}
          onChange={setAccountId} options={accounts.options} placeholder="Escolher na hora" />
        {kind === "pagar" ? (
          <Select label="Tipo de despesa" value={nature} onChange={setNature} options={NATURES} placeholder="Não informar" />
        ) : (
          <Checkbox label="É minha renda principal (ex.: salário)" checked={main} onChange={setMain} />
        )}
      </div>
      <SubmitButton busy={submit.busy} online={online}>Salvar</SubmitButton>
    </form>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <NewBill />
    </Suspense>
  );
}
