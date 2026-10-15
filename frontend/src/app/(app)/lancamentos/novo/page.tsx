"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, Suspense, useState } from "react";

import { useShell } from "@/components/Shell";
import {
  BackLink,
  DateInput,
  Empty,
  ErrorBox,
  FormError,
  Loading,
  MoneyInput,
  PageHeader,
  Segmented,
  Select,
  SubmitButton,
  TextInput,
  useScrollToError,
} from "@/components/ui";
import { api } from "@/lib/api";
import { todayInSaoPaulo } from "@/lib/dates";
import { useSubmit } from "@/lib/hooks";
import { NATURES, useAccounts, useCategories } from "@/lib/options";

type Kind = "despesa" | "receita" | "transferencia" | "reembolso";

const TITLES: Record<Kind, string> = {
  despesa: "Registrar despesa",
  receita: "Registrar receita",
  transferencia: "Transferir entre contas",
  reembolso: "Registrar reembolso",
};

const SAVED: Record<Kind, string> = {
  despesa: "Despesa salva.",
  receita: "Receita salva.",
  transferencia: "Transferência salva.",
  reembolso: "Reembolso salvo.",
};

function NewTransaction() {
  const params = useSearchParams();
  const router = useRouter();
  const { online, flash } = useShell();
  const initial = (params.get("tipo") as Kind | null) ?? "despesa";
  const [kind, setKind] = useState<Kind>(TITLES[initial] ? initial : "despesa");
  const accounts = useAccounts();
  const categories = useCategories(kind === "receita" ? "receita" : "despesa");
  const submit = useSubmit();
  useScrollToError(submit.error);

  const [amount, setAmount] = useState<number | null>(null);
  const [description, setDescription] = useState("");
  const [accountId, setAccountId] = useState(params.get("conta") ?? "");
  const [toAccountId, setToAccountId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [date, setDate] = useState(todayInSaoPaulo());
  const [nature, setNature] = useState("");
  const [note, setNote] = useState("");

  const account = accountId || accounts.options[0]?.value || "";
  const changeKind = (k: Kind) => {
    setKind(k);
    setCategoryId("");
  };

  if (accounts.state === "loading") return <Loading />;
  if (accounts.state === "error") return <ErrorBox message={accounts.message} onRetry={accounts.reload} />;
  if (accounts.options.length === 0) {
    return (
      <Empty title="Primeiro, cadastre uma conta" action={<Link className="btn" href="/contas/nova/">Cadastrar conta</Link>}>
        Para registrar receitas e despesas, você precisa de pelo menos uma conta (banco ou dinheiro em espécie).
      </Empty>
    );
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (amount === null) return submit.setError("Informe o valor.");
    const ok = await submit.run((key) => {
      if (kind === "transferencia") {
        return api.create("/transferencias", {
          from_account_id: account, to_account_id: toAccountId, amount_cents: amount, tx_date: date,
          description: description || null, note: note || null,
        }, key);
      }
      return api.create("/lancamentos", {
        kind, account_id: account, amount_cents: amount, tx_date: date, description,
        category_id: categoryId || null, expense_nature: kind === "despesa" && nature ? nature : null,
        note: note || null,
      }, key);
    });
    if (ok) {
      flash(SAVED[kind]);
      router.push("/lancamentos/");
    }
  };

  const f = submit.fields;
  return (
    <form className="stack-lg" onSubmit={onSubmit} noValidate>
      <BackLink href="/lancamentos/">Receitas e despesas</BackLink>
      <PageHeader title={TITLES[kind]} />
      <Segmented<Kind> label="O que você quer registrar?" value={kind} onChange={changeKind} options={[
        { value: "despesa", label: "Despesa" },
        { value: "receita", label: "Receita" },
        { value: "transferencia", label: "Transferência" },
      ]} />
      <FormError error={submit.error} />
      <div className="stack">
        <MoneyInput label="Valor" cents={amount} onChange={setAmount} error={f.amount_cents} />
        {kind === "transferencia" ? (
          <>
            <Select label="Sai da conta" value={account} onChange={setAccountId} options={accounts.options}
              error={f.from_account_id ?? f.account_id} />
            <Select label="Entra na conta" value={toAccountId} onChange={setToAccountId}
              options={accounts.options.filter((o) => o.value !== account)} placeholder="Escolha a conta"
              error={f.to_account_id} hint="Transferência entre suas contas não conta como receita nem como gasto." />
          </>
        ) : (
          <>
            <TextInput label="Descrição" value={description} onChange={setDescription} error={f.description}
              hint={kind === "despesa" ? "Ex.: Mercado, Farmácia, Conta de luz" : "Ex.: Salário, Aposentadoria"} />
            <Select label={kind === "receita" ? "Conta onde o dinheiro entrou" : "Conta de onde o dinheiro saiu"}
              value={account} onChange={setAccountId} options={accounts.options} error={f.account_id} />
            <Select label="Categoria" value={categoryId} onChange={setCategoryId} options={categories.options}
              placeholder="Sem categoria" error={f.category_id} />
          </>
        )}
        <DateInput label="Data" value={date} onChange={setDate} max={todayInSaoPaulo()} error={f.tx_date}
          hint="Para algo que ainda vai acontecer, use Contas a pagar." />
        <details className="more">
          <summary>Mais detalhes (opcional)</summary>
          <div className="stack" style={{ marginTop: 8 }}>
            {kind === "transferencia" ? (
              <TextInput label="Descrição" value={description} onChange={setDescription} error={f.description} />
            ) : null}
            {kind === "despesa" ? (
              <Select label="Tipo de despesa" value={nature} onChange={setNature} options={NATURES} placeholder="Não informar" />
            ) : null}
            <TextInput label="Observação" value={note} onChange={setNote} maxLength={500} error={f.note} />
            {kind === "despesa" ? (
              <p className="small muted">
                Recebeu dinheiro de volta de um gasto? <button type="button" className="btn ghost" onClick={() => changeKind("reembolso")}>Registrar reembolso</button>
              </p>
            ) : null}
          </div>
        </details>
      </div>
      <SubmitButton busy={submit.busy} online={online}>Salvar</SubmitButton>
    </form>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <NewTransaction />
    </Suspense>
  );
}
