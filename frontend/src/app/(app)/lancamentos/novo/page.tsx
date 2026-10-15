"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, Suspense, useState } from "react";

import { useShell } from "@/components/Shell";
import {
  BackLink,
  CategoryPicker,
  DateInput,
  Empty,
  ErrorBox,
  FormError,
  Loading,
  MoneyInput,
  NumberInput,
  PageHeader,
  Segmented,
  Select,
  SubmitButton,
  TextInput,
  useScrollToError,
} from "@/components/ui";
import { api } from "@/lib/api";
import { addMonthsIso, todayInSaoPaulo } from "@/lib/dates";
import { formatCents, formatIsoDate, splitInstallments } from "@/lib/format";
import { useApi, useSubmit } from "@/lib/hooks";
import { CATEGORY_HINTS, NATURES, useAccounts, useCategories } from "@/lib/options";
import type { Card } from "@/lib/types";

type Kind = "despesa" | "receita" | "transferencia" | "reembolso";
type PayMode = "avista" | "cartao" | "carne";
type Frequency = "mensal" | "semanal" | "anual";

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

const FREQUENCIES: { value: Frequency; label: string }[] = [
  { value: "mensal", label: "Todo mês" },
  { value: "semanal", label: "Toda semana" },
  { value: "anual", label: "Todo ano" },
];

/** "10x de R$ 100,00" ou, com resto, "1ª de R$ 333,34 e 2x de R$ 333,33". */
function installmentsText(total: number | null, count: number): string | null {
  if (total === null || count < 2) return null;
  const parts = splitInstallments(total, count);
  const [first, rest] = [parts[0], parts[1]];
  if (first === undefined || rest === undefined || rest === 0) return null;
  if (first === rest) return `${count}x de ${formatCents(rest)}`;
  return `1ª de ${formatCents(first)} e ${count - 1}x de ${formatCents(rest)}`;
}

function NewTransaction() {
  const params = useSearchParams();
  const router = useRouter();
  const { online, flash } = useShell();
  const initial = (params.get("tipo") as Kind | null) ?? "despesa";
  const [kind, setKind] = useState<Kind>(TITLES[initial] ? initial : "despesa");
  const accounts = useAccounts();
  const categories = useCategories(kind === "receita" ? "receita" : "despesa");
  const cards = useApi<Card[]>("/cartoes");
  const submit = useSubmit();
  useScrollToError(submit.error);

  const [amount, setAmount] = useState<number | null>(null);
  const [description, setDescription] = useState("");
  const [accountId, setAccountId] = useState(params.get("conta") ?? "");
  const [toAccountId, setToAccountId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [date, setDate] = useState(todayInSaoPaulo());
  const [payMode, setPayMode] = useState<PayMode>("avista");
  const [cardId, setCardId] = useState("");
  const [count, setCount] = useState("2");
  const [firstDue, setFirstDue] = useState("");
  const [repeats, setRepeats] = useState<"nao" | "sim">("nao");
  const [frequency, setFrequency] = useState<Frequency>("mensal");
  const [nature, setNature] = useState("");
  const [note, setNote] = useState("");

  const account = accountId || accounts.options[0]?.value || "";
  const cardOptions = cards.state === "ready"
    ? cards.data.filter((c) => c.is_active).map((c) => ({ value: c.id, label: c.name }))
    : [];
  const card = cardId || cardOptions[0]?.value || "";
  const n = Math.trunc(Number(count)) || 0;
  const due = firstDue || addMonthsIso(date, 1);
  const isExpense = kind === "despesa";
  const installment = isExpense && payMode !== "avista";
  const categoryName = categories.options.find((o) => o.value === categoryId)?.label ?? "";

  const changeKind = (k: Kind) => {
    setKind(k);
    setCategoryId("");
    setRepeats("nao");
    setPayMode("avista");
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
    const text = description.trim() || categoryName;
    if (kind !== "transferencia" && !text) {
      return submit.setError(isExpense ? "Escolha com o que foi o gasto." : "Escolha de onde veio o dinheiro.");
    }
    if (installment && (n < (payMode === "carne" ? 2 : 1) || n > 72)) {
      return submit.setError("Informe as parcelas: de 2 a 72.");
    }
    if (payMode === "cartao" && isExpense && !card) return submit.setError("Escolha o cartão.");

    const ok = await submit.run((key) => {
      if (kind === "transferencia") {
        return api.create("/transferencias", {
          from_account_id: account, to_account_id: toAccountId, amount_cents: amount, tx_date: date,
          description: description || null, note: note || null,
        }, key);
      }
      if (isExpense && payMode === "cartao") {
        return api.create(`/cartoes/${card}/compras`, {
          kind: "compra", description: text, total_cents: amount, purchase_date: date, installments_count: n,
          category_id: categoryId || null, note: note || null,
        }, key);
      }
      if (isExpense && payMode === "carne") {
        return api.create("/parcelamentos", {
          description: text, total_cents: amount, installments_count: n, first_due_date: due,
          category_id: categoryId || null, account_id: account, expense_nature: nature || null, note: note || null,
        }, key);
      }
      return api.create("/lancamentos", {
        kind, account_id: account, amount_cents: amount, tx_date: date, description: text,
        category_id: categoryId || null, expense_nature: isExpense && nature ? nature : null,
        note: note || null, repeat: repeats === "sim" && kind !== "reembolso" ? { frequency } : null,
      }, key);
    });
    if (!ok) return;
    if (isExpense && payMode === "cartao") {
      flash(n > 1 ? `Compra salva no cartão em ${n} parcelas.` : "Compra salva no cartão.");
      router.push(`/cartoes/detalhe/?id=${card}`);
    } else if (isExpense && payMode === "carne") {
      flash(`Compra parcelada salva: as ${n} parcelas estão em Contas a pagar.`);
      router.push("/a-pagar/");
    } else {
      flash(repeats === "sim" ? `${SAVED[kind]} As próximas vezes aparecem em Contas a pagar.` : SAVED[kind]);
      router.push("/lancamentos/");
    }
  };

  const f = submit.fields;
  const preview = installment ? installmentsText(amount, n) : null;
  const accountField = accounts.options.length > 1 ? (
    <Select label={kind === "receita" ? "Conta onde o dinheiro entrou" : payMode === "carne" ? "Conta de onde vai sair o pagamento" : "Conta de onde o dinheiro saiu"}
      value={account} onChange={setAccountId} options={accounts.options} error={f.account_id} />
  ) : (
    <p className="small muted">Conta: {accounts.options[0]?.label}</p>
  );

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
        <MoneyInput label={installment ? "Valor total da compra" : "Valor"} cents={amount} onChange={setAmount}
          error={f.amount_cents ?? f.total_cents} />
        {kind === "transferencia" ? (
          <>
            <Select label="Sai da conta" value={account} onChange={setAccountId} options={accounts.options}
              error={f.from_account_id ?? f.account_id} />
            <Select label="Entra na conta" value={toAccountId} onChange={setToAccountId}
              options={accounts.options.filter((o) => o.value !== account)} placeholder="Escolha a conta"
              error={f.to_account_id} hint="Transferência entre suas contas não conta como receita nem como gasto." />
            <DateInput label="Data" value={date} onChange={setDate} max={todayInSaoPaulo()} error={f.tx_date} />
          </>
        ) : (
          <>
            <CategoryPicker label={kind === "receita" ? "De onde veio o dinheiro?" : "Com o que foi o gasto?"}
              value={categoryId} onChange={setCategoryId} options={categories.options} hints={CATEGORY_HINTS}
              error={f.category_id} />

            <DateInput label={isExpense ? "Data da compra" : "Data"} value={date} onChange={setDate} max={todayInSaoPaulo()}
              error={f.tx_date ?? f.purchase_date} hint={installment ? undefined : "Para algo que ainda vai acontecer, use Contas a pagar."} />

            {isExpense ? (
              <Segmented<PayMode> label="Como pagou?" value={payMode} onChange={setPayMode} options={[
                { value: "avista", label: "À vista" },
                ...(cardOptions.length > 0 ? [{ value: "cartao" as const, label: "No cartão" }] : []),
                { value: "carne", label: "Carnê ou boleto" },
              ]} />
            ) : null}

            {installment ? (
              <div className="card stack">
                {payMode === "cartao" ? (
                  <Select label="Cartão" value={card} onChange={setCardId} options={cardOptions} error={f.card_id} />
                ) : null}
                <NumberInput label="Em quantas parcelas?" value={count} onChange={setCount} min={payMode === "carne" ? 2 : 1}
                  max={72} error={f.installments_count} hint={payMode === "cartao" ? "1 = à vista no cartão." : undefined} />
                {payMode === "carne" ? (
                  <DateInput label="1ª parcela vence em" value={due} onChange={setFirstDue} error={f.first_due_date} />
                ) : null}
                {preview ? (
                  <p aria-live="polite"><strong>{preview}</strong>
                    {payMode === "carne" && n >= 2
                      ? <>, de {formatIsoDate(due)} a {formatIsoDate(addMonthsIso(due, n - 1))}.</>
                      : "."}
                  </p>
                ) : null}
                <p className="small muted">
                  {payMode === "cartao"
                    ? "As parcelas entram nas próximas faturas do cartão."
                    : "Cada parcela aparece em Contas a pagar no seu mês. O gasto conta quando você marca a parcela como paga."}
                </p>
              </div>
            ) : null}

            {payMode !== "cartao" || !isExpense ? accountField : null}

            {!installment ? (
              <div className="stack">
                <Segmented<"nao" | "sim"> label="Repete?" value={repeats} onChange={setRepeats} options={[
                  { value: "nao", label: "Só desta vez" },
                  { value: "sim", label: "Repete" },
                ]} />
                {repeats === "sim" ? (
                  <>
                    <Select label="Com que frequência" value={frequency} onChange={(v) => setFrequency(v as Frequency)}
                      options={FREQUENCIES} error={f.repeat} />
                    <p className="small muted">
                      Esta vez fica registrada agora. As próximas aparecem em Contas a pagar
                      {kind === "receita" ? " (a receber)" : ""}, para você confirmar quando acontecerem.
                    </p>
                  </>
                ) : null}
              </div>
            ) : null}

            <TextInput label="Descrição (opcional)" value={description} onChange={setDescription} error={f.description}
              hint={isExpense ? "Ex.: Geladeira, Farmácia do centro. Se ficar em branco, usa o nome escolhido acima." : "Ex.: Salário de outubro"} />
          </>
        )}
        <details className="more">
          <summary>Mais detalhes (opcional)</summary>
          <div className="stack" style={{ marginTop: 8 }}>
            {kind === "transferencia" ? (
              <TextInput label="Descrição" value={description} onChange={setDescription} error={f.description} />
            ) : null}
            {isExpense && payMode !== "cartao" ? (
              <Select label="Tipo de despesa" value={nature} onChange={setNature} options={NATURES} placeholder="Não informar" />
            ) : null}
            <TextInput label="Observação" value={note} onChange={setNote} maxLength={500} error={f.note} />
            {isExpense ? (
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
