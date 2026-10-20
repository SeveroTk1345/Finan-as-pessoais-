"use client";

import { useState } from "react";

import { BackLink, ErrorBox, Loading, MoneyInput, Notice, PageHeader, Stat, TextInput } from "@/components/ui";
import { formatCents, formatIsoDate } from "@/lib/format";
import { useApi, useDebounced } from "@/lib/hooks";

type Plan = {
  month: string;
  income: { used_cents: number; suggested_cents: number; expected_cents: number; average_cents: number; source: "recorrencias" | "media" | "nenhuma" };
  bills: { total_cents: number; items: { label: string; cents: number }[] };
  invest_cents: number;
  invest_suggested_cents: number;
  free_cents: number;
  projection: { years: number; deposited_cents: number; estimated_cents: number }[];
  annual: { description: string; amount_cents: number; next_due: string; months_left: number; per_month_cents: number; steady_cents: number }[];
  warnings: string[];
  tips: string[];
  assumptions: string[];
};

const SOURCE: Record<Plan["income"]["source"], string> = {
  recorrencias: "Pelas receitas que se repetem que você cadastrou.",
  media: "Pela média do que você recebeu nos últimos 3 meses.",
  nenhuma: "Ainda não há receitas cadastradas: informe quanto recebe por mês.",
};

const RATE = /^\d{1,3}([.,]\d{1,2})?$/;

/** Barra com as três partes da renda (preto, cinza e branco, com texto ao lado). */
function SplitBar({ bills, invest, free }: { bills: number; invest: number; free: number }) {
  const total = bills + invest + Math.max(free, 0);
  if (total <= 0) return null;
  const pct = (v: number) => `${Math.max(0, (v * 100) / total)}%`;
  return (
    <div className="split-bar" role="img"
      aria-label={`Contas ${formatCents(bills)}, investir ${formatCents(invest)}, livre ${formatCents(Math.max(free, 0))}`}>
      <span className="seg bills" style={{ width: pct(bills) }} />
      <span className="seg invest" style={{ width: pct(invest) }} />
      <span className="seg free" style={{ width: pct(Math.max(free, 0)) }} />
    </div>
  );
}

function Result({ plan }: { plan: Plan }) {
  const income = plan.income.used_cents;
  const share = (v: number) => (income > 0 ? `${Math.round((v * 100) / income)}% da renda` : undefined);
  return (
    <>
      <section className="card stack" aria-labelledby="divisao">
        <h2 id="divisao">Como dividir {formatCents(income)}</h2>
        <SplitBar bills={plan.bills.total_cents} invest={plan.invest_cents} free={plan.free_cents} />
        <div className="grid-2">
          <Stat size="md" label="■ Contas do mês" cents={plan.bills.total_cents} help={share(plan.bills.total_cents)} />
          <Stat size="md" label="▨ Para investir" cents={plan.invest_cents} help={share(plan.invest_cents)} />
          <Stat size="md" label="□ Livre para gastar" cents={plan.free_cents} signed
            help={plan.free_cents >= 0 ? "Mercado, lazer, roupas e o resto do dia a dia." : "Faltaria dinheiro."} />
        </div>
        <details className="more">
          <summary>De onde vêm as contas do mês</summary>
          <ul className="list" style={{ marginTop: 8 }}>
            {plan.bills.items.map((i) => (
              <li key={i.label} className="list-row">
                <span className="main"><span className="title">{i.label}</span></span>
                <span className="amount">{formatCents(i.cents)}</span>
              </li>
            ))}
          </ul>
        </details>
      </section>
      {plan.warnings.map((w) => <Notice key={w} tone="warn"><p>{w}</p></Notice>)}
      {plan.tips.map((t) => <Notice key={t} tone="pos"><p>{t}</p></Notice>)}
    </>
  );
}

function Projection({ plan }: { plan: Plan }) {
  const withRate = plan.projection.some((p) => p.estimated_cents !== p.deposited_cents);
  return (
    <ul className="list" aria-label="Projeção do investimento">
      {plan.projection.map((p) => (
        <li key={p.years} className="list-row">
          <span className="main">
            <span className="title">Em {p.years === 1 ? "1 ano" : `${p.years} anos`}</span>
            {withRate ? <span className="sub">Você colocou <span className="nowrap">{formatCents(p.deposited_cents)}</span></span> : null}
          </span>
          <strong className="amount">{formatCents(p.estimated_cents)}</strong>
        </li>
      ))}
    </ul>
  );
}

/** Contas de uma vez por ano: quanto separar por mês para não levar susto. */
function Annual({ plan }: { plan: Plan }) {
  const total = plan.annual.reduce((s, a) => s + a.per_month_cents, 0);
  return (
    <section className="card stack" aria-labelledby="anuais">
      <h2 id="anuais">Contas de uma vez por ano</h2>
      {plan.annual.length === 0 ? (
        <p className="muted">
          IPVA, IPTU, seguro, material escolar… Cadastre em Contas a pagar com <strong>Repetir: todo ano</strong> e
          aqui aparece quanto separar por mês.
        </p>
      ) : (
        <>
          <ul className="list">
            {plan.annual.map((a) => (
              <li key={`${a.description}-${a.next_due}`} className="list-row">
                <span className="main">
                  <span className="title">{a.description}</span>
                  <span className="sub"><span className="nowrap">{formatCents(a.amount_cents)}</span>.{" "}
                    {a.months_left === 0
                      ? <>Vence neste mês ({formatIsoDate(a.next_due)}).</>
                      : <>Vence em {formatIsoDate(a.next_due)}. Faltam {a.months_left === 1 ? "1 mês" : `${a.months_left} meses`}.</>}
                  </span>
                </span>
                <span className="amount">{formatCents(a.per_month_cents)}<span className="small muted">{a.months_left ? " por mês" : ""}</span></span>
              </li>
            ))}
          </ul>
          <p>Separando <strong>{formatCents(total)} por mês</strong>, o dinheiro estará pronto em cada vencimento.
            Depois disso, o ritmo de todo ano é de {formatCents(plan.annual.reduce((s, a) => s + a.steady_cents, 0))} por mês.</p>
        </>
      )}
    </section>
  );
}

export default function MonthPlanPage() {
  const base = useApi<Plan>("/plano-do-mes");
  const [income, setIncome] = useState<number | null>(null);
  const [invest, setInvest] = useState<number | null>(null);
  const [rate, setRate] = useState("");

  const rateOk = rate === "" || RATE.test(rate.trim());
  const query = new URLSearchParams();
  if (income !== null) query.set("renda", String(income));
  if (invest !== null) query.set("investir", String(invest));
  if (rate && rateOk) query.set("taxa", rate.trim().replace(",", "."));
  const qs = useDebounced(query.toString());
  const calc = useApi<Plan>(qs ? `/plano-do-mes?${qs}` : "/plano-do-mes");

  if (base.state === "loading") return <Loading />;
  if (base.state === "error") return <ErrorBox message={base.message} onRetry={base.reload} />;
  const plan = calc.state === "ready" ? calc.data : null;

  return (
    <div className="stack-lg">
      <BackLink href="/planejamento/">Planejamento</BackLink>
      <PageHeader title="Plano do mês"
        subtitle="Uma sugestão de como dividir a sua renda entre as contas, o investimento e o dia a dia. Você decide." />

      <section className="card stack">
        <MoneyInput label="Quanto você recebe por mês" cents={income ?? base.data.income.suggested_cents}
          onChange={setIncome} allowZero hint={income === null ? SOURCE[base.data.income.source] : "Valor informado por você."} />
        <MoneyInput label="Quanto quer investir por mês" cents={invest ?? plan?.invest_suggested_cents ?? base.data.invest_suggested_cents}
          onChange={setInvest} allowZero
          hint={invest === null ? "Sugestão: 20% da renda, sem passar do que sobra depois das contas." : "Valor escolhido por você."} />
        {income !== null || invest !== null ? (
          <button type="button" className="btn ghost" onClick={() => { setIncome(null); setInvest(null); }}>
            Voltar para a sugestão
          </button>
        ) : null}
      </section>

      <div aria-live="polite" className="stack-lg">
        {plan ? <Result plan={plan} /> : calc.state === "error" ? <ErrorBox message={calc.message} onRetry={calc.reload} /> : <Loading />}
      </div>

      <section className="card stack" aria-labelledby="proj">
        <h2 id="proj">Se investir {formatCents(plan?.invest_cents ?? base.data.invest_cents)} por mês</h2>
        <TextInput label="Quanto rende ao ano, em % (opcional)" value={rate} onChange={setRate} maxLength={6}
          error={rateOk ? undefined : "Use só números, como 10 ou 10,5."}
          hint="Veja a taxa do seu investimento no banco ou na corretora. Sem taxa, mostra só a soma dos depósitos." />
        {plan ? <Projection plan={plan} /> : null}
      </section>

      {plan ? <Annual plan={plan} /> : null}

      {plan ? (
        <ul className="small muted" style={{ margin: 0, paddingLeft: 20 }}>
          {plan.assumptions.map((a) => <li key={a}>{a}</li>)}
        </ul>
      ) : null}
    </div>
  );
}
