"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { type FormEvent, Suspense, useState } from "react";

import { useShell } from "@/components/Shell";
import {
  CategoryPicker,
  BackLink, ConfirmButton, DateInput, DateText, ErrorBox, FormError, Loading, Money, MoneyInput, NumberInput, PageHeader, Segmented,
  Situation, Stat, SubmitButton, TextInput, useScrollToError,
} from "@/components/ui";
import { api } from "@/lib/api";
import { todayInSaoPaulo } from "@/lib/dates";
import { formatCents } from "@/lib/format";
import { orderInvoices } from "@/lib/invoices";
import { useApi, useSubmit } from "@/lib/hooks";
import { CATEGORY_HINTS, useCategories } from "@/lib/options";
import type { Card } from "@/lib/types";

function PurchaseForm({ card, onDone }: { card: Card; onDone: () => void }) {
  const { online, flash } = useShell();
  const categories = useCategories("despesa");
  const submit = useSubmit();
  useScrollToError(submit.error);
  const [kind, setKind] = useState<"compra" | "encargo">("compra");
  const [description, setDescription] = useState("");
  const [total, setTotal] = useState<number | null>(null);
  const [date, setDate] = useState(todayInSaoPaulo());
  const [count, setCount] = useState("1");
  const [categoryId, setCategoryId] = useState("");
  const n = Math.max(1, Number(count) || 1);
  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (total === null) return submit.setError("Informe o valor.");
    const ok = await submit.run((key) =>
      api.create(`/cartoes/${card.id}/compras`, {
        kind, description, total_cents: total, purchase_date: date, installments_count: kind === "encargo" ? 1 : n,
        category_id: categoryId || null,
      }, key),
    );
    if (ok) {
      flash(kind === "compra" && n > 1 ? `Compra salva em ${n} parcelas.` : "Compra salva.");
      setDescription("");
      setTotal(null);
      setCount("1");
      onDone();
    }
  };
  const f = submit.fields;
  return (
    <form className="card stack" onSubmit={onSubmit} noValidate id="nova-compra">
      <h2>Registrar compra no cartão</h2>
      <Segmented label="Tipo" value={kind} onChange={setKind}
        options={[{ value: "compra", label: "Compra" }, { value: "encargo", label: "Tarifa, juros ou IOF" }]} />
      <FormError error={submit.error} />
      <TextInput label="Descrição" value={description} onChange={setDescription} error={f.description}
        hint={kind === "compra" ? "Ex.: Farmácia, Geladeira" : "Ex.: Anuidade, IOF, Juros do rotativo"} />
      <MoneyInput label="Valor total" cents={total} onChange={setTotal} error={f.total_cents} />
      {kind === "compra" ? (
        <NumberInput label="Em quantas parcelas?" value={count} onChange={setCount} max={72} error={f.installments_count}
          hint={total && n > 1 ? `${n} parcelas de cerca de ${formatCents(Math.floor(total / n))}.` : "1 = à vista."} />
      ) : null}
      <DateInput label="Data da compra" value={date} onChange={setDate} max={todayInSaoPaulo()} error={f.purchase_date} />
      {kind === "compra" ? (
        <CategoryPicker label="Com o que foi a compra?" value={categoryId} onChange={setCategoryId} options={categories.options} hints={CATEGORY_HINTS} />
      ) : null}
      <SubmitButton busy={submit.busy} online={online}>Salvar compra</SubmitButton>
    </form>
  );
}

function EditCard({ card, onDone }: { card: Card; onDone: () => void }) {
  const { online, flash } = useShell();
  const [name, setName] = useState(card.name);
  const [limit, setLimit] = useState<number | null>(card.limit_cents);
  const [closing, setClosing] = useState(String(card.closing_day));
  const [due, setDue] = useState(String(card.due_day));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.patch(`/cartoes/${card.id}`, { name, limit_cents: limit ?? 0, closing_day: Number(closing), due_day: Number(due), version: card.version });
      flash("Cartão atualizado. Compras já lançadas continuam nas faturas originais.");
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="stack" onSubmit={onSubmit} noValidate>
      <FormError error={error} />
      <TextInput label="Nome" value={name} onChange={setName} maxLength={60} />
      <MoneyInput label="Limite total" cents={limit} onChange={setLimit} allowZero />
      <NumberInput label="Dia do fechamento" value={closing} onChange={setClosing} max={31} />
      <NumberInput label="Dia do vencimento" value={due} onChange={setDue} max={31} />
      <SubmitButton busy={busy} online={online}>Salvar</SubmitButton>
    </form>
  );
}

function Detail({ id }: { id: string }) {
  const { online, flash } = useShell();
  const card = useApi<Card>(`/cartoes/${id}`);
  if (card.state === "loading") return <Loading />;
  if (card.state === "error") return <ErrorBox message={card.message} onRetry={card.reload} />;
  const c = card.data;
  const invoices = orderInvoices(c.invoices ?? []);
  return (
    <div className="stack-lg">
      <BackLink href="/cartoes/">Cartões</BackLink>
      <PageHeader title={c.name} subtitle={`Fecha dia ${c.closing_day} · vence dia ${c.due_day}`} />
      <div className="card grid-2">
        <Stat size="md" label="Limite disponível" cents={c.limit_available_cents} help={<>Limite total <Money cents={c.limit_cents} /></>} />
        <Stat size="md" label="Limite usado" cents={c.limit_used_cents}
          help="Inclui parcelas futuras. Cada parcela conta uma vez só." />
        {c.credit_balance_cents > 0 ? <Stat size="md" label="Crédito no cartão" cents={c.credit_balance_cents} /> : null}
      </div>
      <a className="btn" href="#nova-compra">+ Registrar compra</a>

      <section className="stack" aria-labelledby="faturas">
        <h2 id="faturas">Faturas</h2>
        <ul className="list">
          {invoices.map((i) => (
            <li key={i.due_date}>
              <Link className="list-row" href={`/cartoes/fatura/?id=${c.id}&venc=${i.due_date}`}>
                <span className="main">
                  <span className="title">Vence <DateText iso={i.due_date} /></span>
                  <span className="sub">Fecha <DateText iso={i.closing_date} /></span>
                  <span className="row" style={{ marginTop: 4, gap: 6 }}>
                    {(i.status === "aberta" || i.status === "futura") && i.total_cents > 0 && i.remaining_cents === 0 ? (
                      <><Situation value="paga" /><span className="small muted">antecipada</span></>
                    ) : <Situation value={i.status} />}
                  </span>
                </span>
                <span style={{ textAlign: "right" }}>
                  <Money cents={i.total_cents} className="amount" />
                  {i.remaining_cents > 0 && i.remaining_cents !== i.total_cents ? (
                    <span className="sub small" style={{ display: "block" }}>falta {formatCents(i.remaining_cents)}</span>
                  ) : null}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      {c.is_active ? <PurchaseForm card={c} onDone={card.reload} /> : null}

      <details className="card more">
        <summary>Editar cartão</summary>
        <div style={{ marginTop: 8 }}><EditCard key={c.version} card={c} onDone={card.reload} /></div>
      </details>
      <ConfirmButton tone="secondary" label={c.is_active ? "Desativar cartão" : "Reativar cartão"}
        title={c.is_active ? "Desativar este cartão?" : "Reativar este cartão?"}
        message={<p>{c.is_active ? "Não será possível lançar compras novas. Faturas e histórico continuam." : "O cartão volta a aceitar compras."}</p>}
        confirmLabel={c.is_active ? "Desativar" : "Reativar"} disabled={!online}
        onConfirm={async () => {
          await api.patch(`/cartoes/${c.id}`, { is_active: !c.is_active, version: c.version });
          flash(c.is_active ? "Cartão desativado." : "Cartão reativado.");
          card.reload();
        }} />
    </div>
  );
}

function Inner() {
  const id = useSearchParams().get("id");
  if (!id) return <ErrorBox message="Cartão não informado." />;
  return <Detail id={id} />;
}

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <Inner />
    </Suspense>
  );
}
