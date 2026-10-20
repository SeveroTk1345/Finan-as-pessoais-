"use client";

import { type FormEvent, useState } from "react";

import {
  BackLink, Badge, DateInput, FormError, Money, MoneyInput, Notice, NumberInput, PageHeader, Segmented, Select, Stat,
} from "@/components/ui";
import { api } from "@/lib/api";
import { shortMonthLabel, todayInSaoPaulo } from "@/lib/dates";
import { formatCents } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Card } from "@/lib/types";

type Result = {
  available_now_cents: number;
  available_after_cents: number;
  monthly_extra_cents: number;
  months: { month: string; income_cents: number; obligations_cents: number; purchase_cents: number; balance_without_cents: number; balance_with_cents: number }[];
  risky_months: string[];
  limit: { card_name: string; available_before_cents: number; available_after_cents: number } | null;
  reserve: { saved_cents: number; needed_cents: number; covers: boolean };
  compare: { buy_now_min_cents: number; dont_buy_min_cents: number; wait_until: string | null };
  verdict: { level: "ok" | "cuidado" | "atencao"; message: string };
  warnings: string[];
  assumptions: string[];
};

export default function CanIBuyPage() {
  const cards = useApi<Card[]>("/cartoes");
  const [amount, setAmount] = useState<number | null>(null);
  const [method, setMethod] = useState<"conta" | "cartao">("conta");
  const [cardId, setCardId] = useState("");
  const [count, setCount] = useState("1");
  const [date, setDate] = useState(todayInSaoPaulo());
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const cardOptions = cards.state === "ready" ? cards.data.filter((c) => c.is_active).map((c) => ({ value: c.id, label: c.name })) : [];
  const card = cardId || cardOptions[0]?.value || "";

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (amount === null) return setError("Informe o valor da compra.");
    setBusy(true);
    setError(null);
    try {
      setResult(await api.post<Result>("/simulador/compra", {
        amount_cents: amount, method, card_id: method === "cartao" ? card : null,
        installments_count: method === "cartao" ? Math.max(1, Number(count) || 1) : 1, purchase_date: date, months: 6,
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro.");
      setResult(null);
    } finally {
      setBusy(false);
    }
  };

  const tone = result?.verdict.level === "ok" ? "pos" : result?.verdict.level === "atencao" ? "neg" : "warn";
  return (
    <div className="stack-lg">
      <BackLink href="/planejamento/">Planejamento</BackLink>
      <PageHeader title="Posso comprar?" subtitle="Veja como uma compra afeta os próximos meses. Nada é registrado." />
      <form className="card stack" onSubmit={onSubmit} noValidate>
        <FormError error={error} />
        <MoneyInput label="Valor da compra" cents={amount} onChange={setAmount} />
        <Segmented label="Como vai pagar" value={method} onChange={setMethod}
          options={[{ value: "conta", label: "À vista (conta ou dinheiro)" }, { value: "cartao", label: "No cartão" }]} />
        {method === "cartao" ? (
          cardOptions.length === 0 ? <p className="muted">Cadastre um cartão em Mais → Cartões para simular.</p> : (
            <>
              <Select label="Cartão" value={card} onChange={setCardId} options={cardOptions} />
              <NumberInput label="Parcelas" value={count} onChange={setCount} max={72} />
            </>
          )
        ) : null}
        <DateInput label="Quando pretende comprar" value={date} onChange={setDate} />
        <button type="submit" className="btn block" disabled={busy}>{busy ? "Calculando…" : "Simular"}</button>
      </form>

      {result ? (
        <section className="stack-lg" aria-live="polite" aria-label="Resultado da simulação">
          <Notice tone={tone} title={result.verdict.level === "ok" ? "Pelas contas registradas, cabe" : result.verdict.level === "atencao" ? "Atenção" : "Cuidado"}>
            <p>{result.verdict.message}</p>
          </Notice>
          {result.warnings.map((w) => <Notice key={w} tone="warn"><p>{w}</p></Notice>)}
          <div className="card grid-2">
            <Stat size="md" label="Dinheiro disponível hoje" cents={result.available_now_cents} />
            {method === "conta" ? <Stat size="md" label="Depois da compra" cents={result.available_after_cents} signed /> : (
              <Stat size="md" label="Parcela por mês" cents={result.monthly_extra_cents} help="Soma-se às outras contas do mês." />
            )}
            {result.limit ? (
              <Stat size="md" label={`Limite disponível do ${result.limit.card_name} depois`} cents={result.limit.available_after_cents}
                help={<>Antes: {formatCents(result.limit.available_before_cents)}. Limite não é dinheiro.</>} />
            ) : null}
          </div>

          <section className="stack">
            <h2>Mês a mês</h2>
            <div className="table-wrap">
              <table className="data">
                <caption className="sr-only">Dinheiro previsto no fim de cada mês, sem e com a compra</caption>
                <thead><tr><th>Mês</th><th className="num">Sem a compra</th><th className="num">Com a compra</th></tr></thead>
                <tbody>
                  {result.months.map((m) => (
                    <tr key={m.month}>
                      <td>{shortMonthLabel(m.month)}{m.balance_with_cents < 0 ? <> <Badge tone="neg">Falta</Badge></> : null}</td>
                      <td className="num"><Money cents={m.balance_without_cents} /></td>
                      <td className="num"><Money cents={m.balance_with_cents} className={m.balance_with_cents < 0 ? "neg" : ""} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="small muted">Saldo previsto no fim de cada mês: dinheiro de hoje + receitas previstas − contas, faturas e parcelas.</p>
          </section>

          <section className="card stack">
            <h2>Comparando</h2>
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              <li>Comprar agora: o menor saldo previsto fica em <strong>{formatCents(result.compare.buy_now_min_cents)}</strong>.</li>
              <li>Não comprar: o menor saldo previsto fica em <strong>{formatCents(result.compare.dont_buy_min_cents)}</strong>.</li>
              <li>{result.compare.wait_until
                ? <>Esperar: comprando à vista a partir de <strong>{shortMonthLabel(result.compare.wait_until)}</strong>, nenhum mês fica negativo.</>
                : "Esperar: no período simulado, não há mês em que a compra à vista caiba sem deixar algum mês negativo."}</li>
            </ul>
            {result.reserve.needed_cents > 0 ? (
              <p>
                Para cobrir a falta, seria preciso usar {formatCents(result.reserve.needed_cents)} da reserva de emergência
                {result.reserve.saved_cents ? ` (você tem ${formatCents(result.reserve.saved_cents)} guardados).` : " (nenhuma reserva cadastrada)."}
              </p>
            ) : null}
          </section>
          <ul className="small muted" style={{ margin: 0, paddingLeft: 20 }}>{result.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
        </section>
      ) : null}
    </div>
  );
}
