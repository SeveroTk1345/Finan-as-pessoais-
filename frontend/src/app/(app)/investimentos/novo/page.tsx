"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, Suspense, useState } from "react";

import { useShell } from "@/components/Shell";
import {
  BackLink, Checkbox, DateInput, Field, FormError, Loading, MoneyInput, PageHeader, Segmented, Select, SubmitButton, TextInput, useScrollToError,
} from "@/components/ui";
import { api } from "@/lib/api";
import { todayInSaoPaulo } from "@/lib/dates";
import { useSubmit } from "@/lib/hooks";
import { useAccounts } from "@/lib/options";

type Klass = "renda_fixa" | "renda_variavel" | "outros";

const PRODUCTS: Record<Klass, string[]> = {
  renda_fixa: ["CDB", "RDB", "Tesouro Direto", "LCI", "LCA", "Poupança", "Debênture", "Outro"],
  renda_variavel: ["Ação", "ETF", "Fundo imobiliário (FII)", "BDR", "Outro"],
  outros: ["Fundo de investimento", "Previdência", "Criptomoeda", "Outro"],
};

function NewInvestment() {
  const params = useSearchParams();
  const router = useRouter();
  const { online, flash } = useShell();
  const accounts = useAccounts();
  const submit = useSubmit();
  useScrollToError(submit.error);
  const initial = params.get("classe") as Klass | null;
  const [klass, setKlass] = useState<Klass>(initial && PRODUCTS[initial] ? initial : "renda_fixa");
  const [product, setProduct] = useState(PRODUCTS[klass][0] ?? "Outro");
  const [name, setName] = useState("");
  const [institution, setInstitution] = useState("");
  const [ticker, setTicker] = useState("");
  const [indexer, setIndexer] = useState("");
  const [rate, setRate] = useState("");
  const [maturity, setMaturity] = useState("");
  const [amount, setAmount] = useState<number | null>(null);
  const [quantity, setQuantity] = useState("");
  const [date, setDate] = useState(todayInSaoPaulo());
  const [fromAccount, setFromAccount] = useState(false);
  const [accountId, setAccountId] = useState("");

  const changeClass = (k: Klass) => {
    setKlass(k);
    setProduct(PRODUCTS[k][0] ?? "Outro");
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const rv = klass === "renda_variavel";
    const first = amount
      ? {
          kind: rv ? "compra" : "aporte", movement_date: date, amount_cents: amount,
          quantity: rv ? quantity.replace(",", ".") || null : null,
          account_id: fromAccount ? accountId || accounts.options[0]?.value : null,
        }
      : null;
    const ok = await submit.run((key) =>
      api.create("/investimentos", {
        asset_class: klass, product_type: product, name: name || product, institution: institution || null,
        ticker: rv ? ticker.trim().toUpperCase() || null : null, indexer: klass === "renda_fixa" && indexer ? indexer : null,
        rate_description: rate || null, maturity_date: maturity || null, first_movement: first,
      }, key),
    );
    if (ok) {
      flash("Investimento cadastrado.");
      router.push("/investimentos/");
    }
  };
  const f = submit.fields;
  return (
    <form className="stack-lg" onSubmit={onSubmit} noValidate>
      <BackLink href="/investimentos/">Investimentos</BackLink>
      <PageHeader title="Novo investimento" />
      <Segmented label="Tipo" value={klass} onChange={changeClass}
        options={[{ value: "renda_fixa", label: "Renda fixa" }, { value: "renda_variavel", label: "Renda variável" }, { value: "outros", label: "Outros" }]} />
      <FormError error={submit.error} />
      <div className="stack">
        <Select label="Produto" value={product} onChange={setProduct} options={PRODUCTS[klass].map((p) => ({ value: p, label: p }))} />
        <TextInput label="Nome" value={name} onChange={setName} maxLength={80} error={f.name} hint="Ex.: CDB Banco X 2028, Tesouro IPCA 2035" />
        {klass === "renda_variavel" ? (
          <TextInput label="Código do ativo" value={ticker} onChange={setTicker} maxLength={12} error={f.ticker} hint="Ex.: PETR4, BOVA11, HGLG11" />
        ) : null}
        <TextInput label="Instituição ou corretora (opcional)" value={institution} onChange={setInstitution} maxLength={60} />
        {klass === "renda_fixa" ? (
          <>
            <Select label="Indexador (opcional)" value={indexer} onChange={setIndexer} placeholder="Não sei / não informar"
              options={["CDI", "IPCA", "Selic", "Prefixado", "Outro"].map((v) => ({ value: v, label: v }))} />
            <TextInput label="Taxa contratada (opcional)" value={rate} onChange={setRate} maxLength={60} hint="Como está no contrato. Ex.: 110% do CDI, IPCA + 6%" />
            <DateInput label="Vencimento (opcional)" value={maturity} onChange={setMaturity} />
          </>
        ) : null}
      </div>
      <section className="card stack">
        <h2>{klass === "renda_variavel" ? "Primeira compra (opcional)" : "Primeiro aporte (opcional)"}</h2>
        <MoneyInput label={klass === "renda_variavel" ? "Valor total da compra" : "Valor aplicado"} cents={amount} onChange={setAmount} />
        {klass === "renda_variavel" ? (
          <Field label="Quantidade de cotas ou ações" error={f["first_movement.quantity"]}>
            {(id, d) => <input id={id} className="input" inputMode="decimal" value={quantity} aria-describedby={d}
              onChange={(e) => setQuantity(e.target.value.replace(/[^0-9,]/g, "").slice(0, 20))} />}
          </Field>
        ) : null}
        <DateInput label="Data" value={date} onChange={setDate} max={todayInSaoPaulo()} />
        <Checkbox label="O dinheiro saiu de uma das minhas contas" checked={fromAccount} onChange={setFromAccount} />
        {fromAccount ? (
          <Select label="Conta" value={accountId || accounts.options[0]?.value || ""} onChange={setAccountId} options={accounts.options}
            hint="A saída aparece na conta, mas não conta como gasto." />
        ) : null}
      </section>
      <SubmitButton busy={submit.busy} online={online}>Salvar investimento</SubmitButton>
    </form>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <NewInvestment />
    </Suspense>
  );
}
