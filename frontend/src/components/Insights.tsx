"use client";

import Link from "next/link";

import { Notice } from "@/components/ui";
import { formatCents } from "@/lib/format";
import { useApi } from "@/lib/hooks";

export type BudgetAlert = {
  category_id: string;
  category_name: string;
  limit_cents: number;
  spent_cents: number;
  percent: number;
  level: "perto" | "passou";
};

type Shortcut = {
  description: string;
  category_id: string | null;
  category_name: string | null;
  amount_cents: number;
  account_id: string;
  times: number;
};

type Summary = { month: string; partial: boolean; lines: string[] };

/** Resumo do mês em frases simples (o backend monta o texto). */
export function MonthSummary({ month, title }: { month: string | null; title: string }) {
  const s = useApi<Summary>(month ? `/relatorios/resumo?mes=${month}` : null);
  if (s.state !== "ready" || s.data.lines.length === 0) return null;
  return (
    <section className="card stack" aria-labelledby="resumo-mes">
      <h2 id="resumo-mes">{title}</h2>
      <ul className="summary-lines">
        {s.data.lines.map((l) => <li key={l}>{l}</li>)}
      </ul>
    </section>
  );
}

/** Avisos de categorias perto do teto ou acima dele. */
export function BudgetAlerts({ alerts }: { alerts: BudgetAlert[] }) {
  if (alerts.length === 0) return null;
  const over = alerts.filter((a) => a.level === "passou");
  return (
    <Notice tone={over.length ? "neg" : "warn"} title={over.length ? "Passou do teto" : "Perto do teto"}>
      <ul style={{ margin: "4px 0 0", paddingLeft: 20 }}>
        {alerts.map((a) => (
          <li key={a.category_id}>
            {a.category_name}: {formatCents(a.spent_cents)} de {formatCents(a.limit_cents)} ({a.percent}%)
          </li>
        ))}
      </ul>
      <p style={{ marginTop: 6 }}><Link href="/planejamento/tetos/">Ver tetos de gastos</Link></p>
    </Notice>
  );
}

/** Atalhos: gastos que se repetem abrem o formulário já preenchido (nada é salvo sem confirmar). */
export function Shortcuts() {
  const s = useApi<Shortcut[]>("/atalhos");
  if (s.state !== "ready" || s.data.length === 0) return null;
  return (
    <section className="stack" aria-labelledby="atalhos">
      <h2 id="atalhos">Gastos de sempre</h2>
      <div className="shortcuts">
        {s.data.map((x) => {
          const q = new URLSearchParams({ tipo: "despesa", valor: String(x.amount_cents), descricao: x.description,
            conta: x.account_id, ...(x.category_id ? { categoria: x.category_id } : {}) });
          return (
            <Link key={`${x.description}-${x.category_id}`} className="btn secondary shortcut" href={`/lancamentos/novo/?${q}`}>
              <span>{x.description}</span>
              <span className="small">{formatCents(x.amount_cents)}</span>
            </Link>
          );
        })}
      </div>
      <p className="small muted">Abre o formulário já preenchido: confira o valor e toque em Salvar.</p>
    </section>
  );
}
