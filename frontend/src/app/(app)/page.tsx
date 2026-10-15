"use client";

import Link from "next/link";

import { useShell } from "@/components/Shell";
import { Badge, DateText, ErrorBox, Loading, Money, Notice, Stat } from "@/components/ui";
import { shortMonthLabel } from "@/lib/dates";
import { formatCents } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Obligation } from "@/lib/types";

type Home = {
  today: string;
  month: string;
  available_cents: number;
  accounts_total_cents: number;
  income_month_cents: number;
  spending_month_cents: number;
  to_pay_month_cents: number;
  committed_cents: number;
  committed_until: string;
  free_cents: number;
  debts_total_cents: number;
  debts_direct_cents: number;
  cards_outstanding_cents: number;
  investments_value_cents: number;
  investments_missing_value: number;
  net_worth_cents: number;
  upcoming: Obligation[];
  overdue_count: number;
  status: { level: "ok" | "cuidado" | "atencao"; message: string };
  explanations: Record<string, string>;
};

type Series = { months: { month: string; income_cents: number; spending_cents: number }[] };

const SOURCE_LINK: Record<string, string> = { conta: "/a-pagar", fatura: "/cartoes", divida: "/dividas" };

export default function HomePage() {
  const { me } = useShell();
  const home = useApi<Home>("/resumo");
  const series = useApi<Series>("/relatorios/evolucao?meses=6");

  if (home.state === "loading") return <Loading />;
  if (home.state === "error") return <ErrorBox message={home.message} onRetry={home.reload} />;
  const h = home.data;
  const tone = h.status.level === "ok" ? "pos" : h.status.level === "atencao" ? "neg" : "warn";

  return (
    <div className="stack-lg">
      <div className="page-head">
        <h1>Olá, {me.nome}</h1>
        <p className="muted">Resumo de <DateText iso={h.today} />.</p>
      </div>

      <Notice tone={tone} title={h.status.level === "ok" ? "Tudo em dia" : "Atenção"}>
        <p>{h.status.message}</p>
      </Notice>

      <section className="card stack" aria-labelledby="disp">
        <h2 id="disp" className="sr-only">Dinheiro disponível</h2>
        <Stat label="Dinheiro disponível hoje" cents={h.available_cents} help={h.explanations.available} />
        <div className="grid-2">
          <Stat size="md" label="Já está comprometido" cents={h.committed_cents}
            help={<>Contas, faturas e parcelas até <DateText iso={h.committed_until} />.</>} />
          <Stat size="md" label="Dinheiro livre estimado" cents={h.free_cents} signed help={h.explanations.free} />
        </div>
      </section>

      <div className="actions" aria-label="Ações rápidas">
        <Link className="btn" href="/lancamentos/novo/?tipo=despesa">+ Registrar despesa</Link>
        <Link className="btn secondary" href="/lancamentos/novo/?tipo=receita">+ Registrar receita</Link>
        <Link className="btn secondary" href="/lancamentos/novo/?tipo=transferencia">Transferir entre contas</Link>
      </div>

      <section className="grid-2" aria-label="Este mês">
        <Link href="/relatorios" className="card card-link">
          <Stat size="md" label="Recebi neste mês" cents={h.income_month_cents} />
        </Link>
        <Link href="/relatorios" className="card card-link">
          <Stat size="md" label="Gastei neste mês" cents={h.spending_month_cents}
            help="Inclui compras no cartão feitas no mês." />
        </Link>
      </section>

      <section className="stack" aria-labelledby="pagar">
        <div className="between">
          <h2 id="pagar">Contas que vencem em breve</h2>
          <Link href="/a-pagar" className="btn ghost">Ver todas</Link>
        </div>
        {h.upcoming.length === 0 ? (
          <p className="muted">Nada para pagar até <DateText iso={h.committed_until} />.</p>
        ) : (
          <ul className="list">
            {h.upcoming.map((o, i) => (
              <li key={`${o.source}-${o.id ?? o.rule_id}-${o.due_date}-${i}`}>
                <Link className="list-row" href={SOURCE_LINK[o.source] ?? "/a-pagar"}>
                  <span className="main">
                    <span className="title">{o.description}</span>
                    <span className="sub">
                      Vence <DateText iso={o.due_date} /> {o.overdue ? <Badge tone="neg">Vencida</Badge> : null}
                    </span>
                  </span>
                  <Money cents={o.amount_cents} className="amount" />
                </Link>
              </li>
            ))}
          </ul>
        )}
        <p className="small muted">Ainda falta pagar neste mês: {formatCents(h.to_pay_month_cents)}.</p>
      </section>

      <section className="grid-2" aria-label="Dívidas e investimentos">
        <Link href="/dividas" className="card card-link">
          <Stat size="md" label="Quanto devo" cents={h.debts_total_cents} help={h.explanations.debts} />
        </Link>
        <Link href="/investimentos" className="card card-link">
          <Stat size="md" label="Quanto tenho investido" cents={h.investments_value_cents}
            help={h.investments_missing_value
              ? `${h.investments_missing_value} investimento(s) sem valor atual informado: contados pelo valor aplicado.`
              : "Pelos últimos valores que você informou."} />
        </Link>
      </section>

      <details className="card more">
        <summary>Como está meu patrimônio?</summary>
        <div className="stack" style={{ marginTop: 8 }}>
          <Stat size="md" label="Patrimônio" cents={h.net_worth_cents} signed help={h.explanations.net_worth} />
          <table className="data">
            <tbody>
              <tr><td>Dinheiro em todas as contas</td><td className="num"><Money cents={h.accounts_total_cents} /></td></tr>
              <tr><td>Investimentos</td><td className="num"><Money cents={h.investments_value_cents} /></td></tr>
              <tr><td>Dívidas</td><td className="num"><Money cents={-h.debts_direct_cents} /></td></tr>
              <tr><td>Cartões (faturas e parcelas)</td><td className="num"><Money cents={-h.cards_outstanding_cents} /></td></tr>
              <tr><th>Total</th><th className="num"><Money cents={h.net_worth_cents} /></th></tr>
            </tbody>
          </table>
        </div>
      </details>

      <section className="stack" aria-labelledby="evol">
        <div className="between">
          <h2 id="evol">Últimos meses</h2>
          <Link href="/relatorios" className="btn ghost">Relatórios</Link>
        </div>
        {series.state === "ready" ? (
          <div className="table-wrap">
            <table className="data">
              <caption className="sr-only">Quanto recebeu e gastou em cada mês</caption>
              <thead><tr><th>Mês</th><th className="num">Recebi</th><th className="num">Gastei</th><th className="num">Sobrou</th></tr></thead>
              <tbody>
                {series.data.months.map((m) => (
                  <tr key={m.month}>
                    <td>{shortMonthLabel(m.month)}</td>
                    <td className="num"><Money cents={m.income_cents} /></td>
                    <td className="num"><Money cents={m.spending_cents} /></td>
                    <td className="num"><Money cents={m.income_cents - m.spending_cents} signed /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : series.state === "error" ? (
          <ErrorBox message={series.message} onRetry={series.reload} />
        ) : (
          <p className="muted">Carregando…</p>
        )}
      </section>
    </div>
  );
}
