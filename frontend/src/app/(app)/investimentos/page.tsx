"use client";

import Link from "next/link";
import { useState } from "react";

import { Badge, Bars, DateText, Empty, ErrorBox, Loading, Money, Notice, PageHeader, Stat } from "@/components/ui";
import { formatAnnualRate as percent } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Investment } from "@/lib/types";

type Overview = {
  items: Investment[];
  totals: {
    invested_cents: number;
    current_value_cents: number;
    missing_value_count: number;
    stale_count: number;
    estimated_gain_cents: number;
    income_received_cents: number;
    annual_return: string | null;
  };
  by_class: { asset_class: string; value_cents: number }[];
  notes: string[];
};

const CLASSES: Record<string, string> = { renda_fixa: "Renda fixa", renda_variavel: "Renda variável", outros: "Outros" };
type Tab = "geral" | "renda_fixa" | "renda_variavel" | "outros";


export default function InvestmentsPage() {
  const [tab, setTab] = useState<Tab>("geral");
  const ov = useApi<Overview>("/investimentos");
  if (ov.state === "loading") return <Loading />;
  if (ov.state === "error") return <ErrorBox message={ov.message} onRetry={ov.reload} />;
  const o = ov.data;
  const list = tab === "geral" ? o.items : o.items.filter((i) => i.asset_class === tab);

  return (
    <div className="stack-lg">
      <PageHeader title="Investimentos" subtitle="Separado do dinheiro do dia a dia."
        action={<Link className="btn" href={`/investimentos/novo/${tab !== "geral" ? `?classe=${tab}` : ""}`}>+ Novo investimento</Link>} />
      <div className="tabs" role="tablist" aria-label="Tipo de investimento">
        {(["geral", "renda_fixa", "renda_variavel", "outros"] as Tab[]).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>{t === "geral" ? "Visão geral" : CLASSES[t]}</button>
        ))}
      </div>

      {o.items.length === 0 ? (
        <Empty title="Nenhum investimento cadastrado" action={<Link className="btn" href="/investimentos/novo/">Cadastrar investimento</Link>}>
          Cadastre CDB, Tesouro Direto, ações, fundos e outros. Você informa os valores; o app não busca cotações na internet.
        </Empty>
      ) : tab === "geral" ? (
        <>
          <div className="card stack">
            <Stat label="Quanto você tem investido" cents={o.totals.current_value_cents}
              help={o.totals.missing_value_count ? `${o.totals.missing_value_count} investimento(s) ainda sem valor atual informado.` : "Pelos últimos valores informados."} />
            <div className="grid-2">
              <Stat size="md" label="Quanto você aplicou" cents={o.totals.invested_cents} help="Aportes menos retiradas. Não é lucro." />
              <Stat size="md" label="Ganho estimado" cents={o.totals.estimated_gain_cents} signed />
            </div>
            {percent(o.totals.annual_return) ? <p>Rentabilidade estimada da carteira: <strong>{percent(o.totals.annual_return)}</strong>.</p> : null}
          </div>
          {o.totals.stale_count ? (
            <Notice tone="warn" title="Valores desatualizados">
              {o.totals.stale_count} investimento(s) com valor informado há mais de 30 dias. Atualize para o resumo ficar correto.
            </Notice>
          ) : null}
          {o.by_class.length > 0 ? (
            <section className="card stack">
              <h2>Como está distribuído</h2>
              <Bars caption="Valor por tipo de investimento" items={o.by_class.map((c) => ({ label: CLASSES[c.asset_class] ?? c.asset_class, cents: c.value_cents }))} />
            </section>
          ) : null}
          <ul className="small muted" style={{ margin: 0, paddingLeft: 20 }}>{o.notes.map((n) => <li key={n}>{n}</li>)}</ul>
        </>
      ) : null}

      {o.items.length > 0 ? (
        list.length === 0 ? <p className="muted">Nenhum investimento deste tipo.</p> : (
          <ul className="list" aria-label="Investimentos">
            {list.map((i) => (
              <li key={i.id}>
                <Link className="list-row" href={`/investimentos/detalhe/?id=${i.id}`}>
                  <span className="main">
                    <span className="title">{i.name}{i.ticker ? ` (${i.ticker})` : ""}</span>
                    <span className="sub">{i.product_type}{i.institution ? ` · ${i.institution}` : ""}</span>
                    <span className="row" style={{ gap: 6, marginTop: 4 }}>
                      {i.value_date ? <span className="small">Valor de <DateText iso={i.value_date} /></span> : <Badge tone="warn">Sem valor atual</Badge>}
                      {i.value_date && i.value_is_stale ? <Badge tone="warn">Desatualizado</Badge> : null}
                      {!i.is_active ? <Badge>Encerrado</Badge> : null}
                    </span>
                  </span>
                  <span style={{ textAlign: "right" }}>
                    <Money cents={i.current_value_cents ?? i.invested_cents} className="amount" />
                    {i.estimated_gain_cents !== null ? <span className="small" style={{ display: "block" }}><Money cents={i.estimated_gain_cents} signed /></span> : null}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )
      ) : null}
    </div>
  );
}
