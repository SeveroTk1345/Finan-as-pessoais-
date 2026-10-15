"use client";

import { useSearchParams } from "next/navigation";
import { type FormEvent, Suspense, useState } from "react";

import { useShell } from "@/components/Shell";
import {
  BackLink, Badge, Checkbox, ConfirmButton, DateInput, DateText, ErrorBox, Field, FormError, Loading, Money, MoneyInput, Notice, PageHeader,
  Select, Stat, SubmitButton, useScrollToError,
} from "@/components/ui";
import { api } from "@/lib/api";
import { todayInSaoPaulo } from "@/lib/dates";
import { formatAnnualRate, formatCents } from "@/lib/format";
import { useApi, useSubmit } from "@/lib/hooks";
import { useAccounts } from "@/lib/options";
import type { Investment } from "@/lib/types";

const KIND_LABELS: Record<string, string> = {
  aporte: "Aporte (coloquei dinheiro)",
  retirada: "Retirada (resgatei)",
  rendimento: "Rendimento",
  dividendo: "Dividendo",
  juros: "Juros / JCP",
  amortizacao: "Amortização (devolução de parte do valor)",
  taxa: "Taxa paga",
  compra: "Compra de cotas/ações",
  venda: "Venda de cotas/ações",
};

function ValueForm({ inv, onDone }: { inv: Investment; onDone: () => void }) {
  const { online, flash } = useShell();
  const submit = useSubmit();
  const rv = inv.asset_class === "renda_variavel";
  const [value, setValue] = useState<number | null>(null);
  const [date, setDate] = useState(todayInSaoPaulo());
  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const ok = await submit.run((key) =>
      api.create(`/investimentos/${inv.id}/valores`, rv ? { unit_price_cents: value, valuation_date: date } : { value_cents: value, valuation_date: date }, key),
    );
    if (ok) {
      flash("Valor atualizado.");
      setValue(null);
      onDone();
    }
  };
  return (
    <form className="card stack" onSubmit={onSubmit} noValidate>
      <h2>{rv ? "Atualizar preço" : "Atualizar saldo"}</h2>
      <p className="small muted">{rv ? "Informe o preço de cada ação ou cota, como aparece na corretora." : "Informe o saldo que aparece no banco ou na corretora."}</p>
      <FormError error={submit.error} />
      <MoneyInput label={rv ? "Preço de cada cota" : "Saldo atual"} cents={value} onChange={setValue} allowZero
        error={submit.fields.value_cents ?? submit.fields.unit_price_cents} />
      <DateInput label="Data do valor" value={date} onChange={setDate} max={todayInSaoPaulo()} />
      <SubmitButton busy={submit.busy} online={online}>Salvar valor</SubmitButton>
    </form>
  );
}

function MovementForm({ inv, onDone }: { inv: Investment; onDone: () => void }) {
  const { online, flash } = useShell();
  const accounts = useAccounts();
  const submit = useSubmit();
  useScrollToError(submit.error);
  const kinds = inv.allowed_kinds ?? [];
  const [kind, setKind] = useState(kinds[0] ?? "aporte");
  const [amount, setAmount] = useState<number | null>(null);
  const [fees, setFees] = useState<number | null>(null);
  const [quantity, setQuantity] = useState("");
  const [date, setDate] = useState(todayInSaoPaulo());
  const [linked, setLinked] = useState(false);
  const [accountId, setAccountId] = useState("");
  const isTrade = kind === "compra" || kind === "venda";
  const isIncome = ["rendimento", "dividendo", "juros"].includes(kind);
  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (amount === null) return submit.setError("Informe o valor.");
    const ok = await submit.run((key) =>
      api.create(`/investimentos/${inv.id}/movimentos`, {
        kind, movement_date: date, amount_cents: amount, fees_cents: fees ?? 0,
        quantity: isTrade ? quantity.replace(",", ".") || null : null,
        account_id: linked ? accountId || accounts.options[0]?.value : null,
        paid_to_account: isIncome && linked,
      }, key),
    );
    if (ok) {
      flash("Movimento registrado.");
      setAmount(null);
      setFees(null);
      setQuantity("");
      onDone();
    }
  };
  return (
    <form className="card stack" onSubmit={onSubmit} noValidate>
      <h2>Registrar movimento</h2>
      <FormError error={submit.error} />
      <Select label="O que aconteceu" value={kind} onChange={setKind} options={kinds.map((k) => ({ value: k, label: KIND_LABELS[k] ?? k }))} />
      <MoneyInput label="Valor" cents={amount} onChange={setAmount} error={submit.fields.amount_cents} />
      {isTrade ? (
        <>
          <Field label="Quantidade" error={submit.fields.quantity}>
            {(id, d) => <input id={id} className="input" inputMode="decimal" value={quantity} aria-describedby={d}
              onChange={(e) => setQuantity(e.target.value.replace(/[^0-9,]/g, "").slice(0, 20))} />}
          </Field>
          <MoneyInput label="Taxas e corretagem (opcional)" cents={fees} onChange={setFees} allowZero />
        </>
      ) : null}
      <DateInput label="Data" value={date} onChange={setDate} max={todayInSaoPaulo()} error={submit.fields.movement_date} />
      <Checkbox label={isIncome ? "Este valor caiu em uma das minhas contas" : "Este dinheiro passou por uma das minhas contas"}
        checked={linked} onChange={setLinked} />
      {linked ? <Select label="Conta" value={accountId || accounts.options[0]?.value || ""} onChange={setAccountId} options={accounts.options} /> : null}
      {isIncome && !linked ? <p className="small muted">Sem conta marcada, o rendimento é tratado como reinvestido.</p> : null}
      <SubmitButton busy={submit.busy} online={online}>Registrar</SubmitButton>
    </form>
  );
}

function Detail({ id }: { id: string }) {
  const { online, flash } = useShell();
  const inv = useApi<Investment>(`/investimentos/${id}`);
  const [error, setError] = useState<string | null>(null);
  if (inv.state === "loading") return <Loading />;
  if (inv.state === "error") return <ErrorBox message={inv.message} onRetry={inv.reload} />;
  const i = inv.data;
  const rv = i.asset_class === "renda_variavel";
  return (
    <div className="stack-lg">
      <BackLink href="/investimentos/">Investimentos</BackLink>
      <PageHeader title={`${i.name}${i.ticker ? ` (${i.ticker})` : ""}`}
        subtitle={[i.product_type, i.institution, i.rate_description, i.maturity_date ? `vence ${i.maturity_date.split("-").reverse().join("/")}` : null].filter(Boolean).join(" · ")} />
      <div className="card stack">
        <Stat label="Valor atual" cents={i.current_value_cents}
          help={i.value_date ? <>Informado em <DateText iso={i.value_date} />.{i.value_is_stale ? " Pode estar desatualizado." : ""}</> : "Ainda não informado. Atualize abaixo."} />
        <div className="grid-2">
          <Stat size="md" label="Quanto você aplicou" cents={i.invested_cents} help={rv ? "Custo das cotas que você tem." : "Aportes menos retiradas."} />
          <Stat size="md" label="Ganho estimado" cents={i.estimated_gain_cents} signed
            help="Valor atual + retiradas + rendimentos recebidos − aportes." />
        </div>
        {rv ? (
          <p>{i.quantity} cota(s) · preço médio {i.average_price_cents !== null && i.average_price_cents !== undefined ? formatCents(i.average_price_cents) : "—"}
            {i.realized_gain_cents ? <> · resultado em vendas <Money cents={i.realized_gain_cents} signed /></> : null}</p>
        ) : null}
        {formatAnnualRate(i.annual_return) ? <p>Rentabilidade estimada: <strong>{formatAnnualRate(i.annual_return)}</strong> (passado não garante futuro).</p> : null}
        {i.value_is_stale ? <Badge tone="warn">Atualize o valor</Badge> : null}
      </div>
      <Notice>Um aporte aumenta o valor aplicado, mas não é lucro. Uma retirada diminui o valor aplicado, mas não é prejuízo.</Notice>
      <FormError error={error} />
      {i.is_active ? (
        <>
          <ValueForm inv={i} onDone={inv.reload} />
          <MovementForm inv={i} onDone={inv.reload} />
        </>
      ) : null}
      <section className="stack">
        <h2>Movimentações</h2>
        {(i.movements ?? []).length === 0 ? <p className="muted">Nenhum movimento registrado.</p> : (
          <ul className="list">
            {(i.movements ?? []).map((m) => (
              <li key={m.id} className="list-row">
                <span className="main">
                  <span className="title">{m.label}{m.quantity ? ` · ${m.quantity.replace(".", ",")} cota(s)` : ""}</span>
                  <span className="sub"><DateText iso={m.movement_date} />{m.account_name ? ` · ${m.account_name}` : ""}{m.status === "cancelado" ? " · cancelado" : ""}</span>
                </span>
                <span className="row" style={{ justifyContent: "flex-end" }}>
                  <Money cents={m.amount_cents} className="amount" />
                  {m.status === "ativo" ? (
                    <ConfirmButton label="Cancelar" tone="secondary" title="Cancelar este movimento?" confirmLabel="Sim, cancelar" disabled={!online}
                      message={<p>O movimento fica no histórico como cancelado{m.account_name ? " e o lançamento na conta também é cancelado" : ""}.</p>}
                      onConfirm={async () => {
                        try {
                          await api.post(`/investimentos/movimentos/${m.id}/cancelar`);
                          flash("Movimento cancelado.");
                          inv.reload();
                        } catch (e) {
                          setError(e instanceof Error ? e.message : "Erro.");
                        }
                      }} />
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
      {(i.valuations ?? []).length > 0 ? (
        <details className="card more">
          <summary>Valores informados</summary>
          <ul className="list" style={{ marginTop: 8 }}>
            {(i.valuations ?? []).map((v) => (
              <li key={v.id} className="list-row">
                <span className="main"><span className="title"><DateText iso={v.valuation_date} /></span></span>
                <Money cents={v.value_cents ?? v.unit_price_cents} className="amount" />
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      <ConfirmButton tone="secondary" label={i.is_active ? "Marcar como encerrado" : "Reabrir investimento"} disabled={!online}
        title={i.is_active ? "Encerrar este investimento?" : "Reabrir este investimento?"}
        message={<p>{i.is_active ? "Ele sai dos totais da carteira. O histórico continua guardado." : "Ele volta a contar na carteira."}</p>}
        confirmLabel={i.is_active ? "Encerrar" : "Reabrir"}
        onConfirm={async () => {
          await api.patch(`/investimentos/${id}`, { is_active: !i.is_active, version: i.version });
          flash(i.is_active ? "Investimento encerrado." : "Investimento reaberto.");
          inv.reload();
        }} />
    </div>
  );
}

function Inner() {
  const id = useSearchParams().get("id");
  if (!id) return <ErrorBox message="Investimento não informado." />;
  return <Detail id={id} />;
}

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <Inner />
    </Suspense>
  );
}
