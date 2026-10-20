"use client";

import { useState } from "react";

import { Bars, ErrorBox, Loading, Money, PageHeader, Stat } from "@/components/ui";
import { monthLabel, monthOf, shiftMonth, shortMonthLabel, todayInSaoPaulo } from "@/lib/dates";
import { useApi } from "@/lib/hooks";
import { MonthSummary } from "@/components/Insights";

type Monthly = {
  month: string;
  income_cents: number;
  spending_cents: number;
  income_by_category: { category: string; cents: number }[];
  spending_by_category: { category: string; cents: number }[];
  cash_in_cents: number;
  cash_out_cents: number;
  start_balance_cents: number;
  end_balance_cents: number;
  bills: Record<"pagar" | "receber", { planned_cents: number; done_cents: number; open_cents: number }>;
  income_committed_percent: number | null;
  notes: string[];
};

type Series = {
  months: { month: string; income_cents: number; spending_cents: number; balance_cents: number; debts_cents: number; investments_cents: number; net_worth_cents: number }[];
  notes: string[];
};

export default function ReportsPage() {
  const [month, setMonth] = useState(monthOf(todayInSaoPaulo()));
  const report = useApi<Monthly>(`/relatorios/mensal?mes=${month}`);
  const series = useApi<Series>("/relatorios/evolucao?meses=12");

  return (
    <div className="stack-lg">
      <PageHeader title="Relatórios" subtitle="Para entender para onde vai o dinheiro." />
      <div className="month-nav" role="group" aria-label="Escolher o mês">
        <button type="button" className="btn secondary" aria-label="Mês anterior" onClick={() => setMonth(shiftMonth(month, -1))}><span aria-hidden="true">←</span> <span className="nav-word">Anterior</span></button>
        <h2 aria-live="polite">{monthLabel(month)}</h2>
        <button type="button" className="btn secondary" aria-label="Próximo mês" onClick={() => setMonth(shiftMonth(month, 1))}><span className="nav-word">Próximo</span> <span aria-hidden="true">→</span></button>
      </div>
      {month <= monthOf(todayInSaoPaulo()) ? (
        <MonthSummary key={month} month={month} title={`Resumo de ${monthLabel(month).toLowerCase()}`} />
      ) : null}
      {report.state === "loading" ? <Loading /> : report.state === "error" ? <ErrorBox message={report.message} onRetry={report.reload} /> : (
        <>
          <section className="card grid-2" aria-label="Resumo do mês">
            <Stat size="md" label="Recebi" cents={report.data.income_cents} />
            <Stat size="md" label="Gastei" cents={report.data.spending_cents} />
            <Stat size="md" label="Sobrou" cents={report.data.income_cents - report.data.spending_cents} signed />
            {report.data.income_committed_percent !== null ? (
              <div><p className="stat-label">Renda comprometida com contas</p><p className="stat-value md">{report.data.income_committed_percent}%</p></div>
            ) : null}
          </section>
          <section className="card stack">
            <h2>Onde gastei</h2>
            {report.data.spending_by_category.length === 0 ? <p className="muted">Nenhum gasto neste mês.</p> : (
              <Bars caption="Gastos por categoria" items={report.data.spending_by_category.map((c) => ({ label: c.category, cents: c.cents }))} />
            )}
          </section>
          {report.data.income_by_category.length > 0 ? (
            <section className="card stack">
              <h2>De onde veio o dinheiro</h2>
              <Bars caption="Receitas por categoria" items={report.data.income_by_category.map((c) => ({ label: c.category, cents: c.cents, tone: "light" as const }))} />
            </section>
          ) : null}
          <section className="card stack">
            <h2>Previsto e realizado</h2>
            <table className="data">
              <thead><tr><th></th><th className="num">Previsto</th><th className="num">Feito</th><th className="num">Falta</th></tr></thead>
              <tbody>
                <tr><td>Contas a pagar</td><td className="num"><Money cents={report.data.bills.pagar.planned_cents} /></td>
                  <td className="num"><Money cents={report.data.bills.pagar.done_cents} /></td><td className="num"><Money cents={report.data.bills.pagar.open_cents} /></td></tr>
                <tr><td>Receitas previstas</td><td className="num"><Money cents={report.data.bills.receber.planned_cents} /></td>
                  <td className="num"><Money cents={report.data.bills.receber.done_cents} /></td><td className="num"><Money cents={report.data.bills.receber.open_cents} /></td></tr>
              </tbody>
            </table>
          </section>
          <section className="card stack">
            <h2>Dinheiro nas contas</h2>
            <table className="data">
              <tbody>
                <tr><td>No começo do mês</td><td className="num"><Money cents={report.data.start_balance_cents} /></td></tr>
                <tr><td>Entrou nas contas</td><td className="num"><Money cents={report.data.cash_in_cents} /></td></tr>
                <tr><td>Saiu das contas (inclui faturas e parcelas pagas)</td><td className="num"><Money cents={-report.data.cash_out_cents} /></td></tr>
                <tr><th>No fim do mês</th><th className="num"><Money cents={report.data.end_balance_cents} /></th></tr>
              </tbody>
            </table>
          </section>
          <ul className="small muted" style={{ margin: 0, paddingLeft: 20 }}>{report.data.notes.map((n) => <li key={n}>{n}</li>)}</ul>
        </>
      )}

      <section className="stack" aria-labelledby="evolucao">
        <h2 id="evolucao">Evolução nos últimos 12 meses</h2>
        {series.state === "loading" ? <Loading /> : series.state === "error" ? <ErrorBox message={series.message} onRetry={series.reload} /> : (
          <>
            <div className="card stack">
              <h3>Patrimônio no fim de cada mês</h3>
              <Bars caption="Patrimônio por mês" items={series.data.months.map((m) => ({ label: shortMonthLabel(m.month), cents: m.net_worth_cents }))} />
            </div>
            <div className="table-wrap">
              <table className="data">
                <caption className="sr-only">Evolução mensal</caption>
                <thead><tr><th>Mês</th><th className="num">Recebi</th><th className="num">Gastei</th><th className="num">Nas contas</th><th className="num">Investido</th><th className="num">Dívidas</th></tr></thead>
                <tbody>
                  {series.data.months.map((m) => (
                    <tr key={m.month}>
                      <td>{shortMonthLabel(m.month)}</td>
                      <td className="num"><Money cents={m.income_cents} /></td>
                      <td className="num"><Money cents={m.spending_cents} /></td>
                      <td className="num"><Money cents={m.balance_cents} /></td>
                      <td className="num"><Money cents={m.investments_cents} /></td>
                      <td className="num"><Money cents={m.debts_cents} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="small muted">{series.data.notes.join(" ")}</p>
          </>
        )}
      </section>
    </div>
  );
}
