"use client";

import Link from "next/link";
import { useState } from "react";

import { Badge, DateText, Empty, ErrorBox, Loading, Money, PageHeader, Select } from "@/components/ui";
import { monthBounds, monthLabel, monthOf, shiftMonth, todayInSaoPaulo } from "@/lib/dates";
import { useApi } from "@/lib/hooks";
import { TX_KINDS, useAccounts } from "@/lib/options";
import type { Transaction } from "@/lib/types";

type Page = { items: Transaction[]; total: number };

export default function TransactionsPage() {
  const [month, setMonth] = useState(monthOf(todayInSaoPaulo()));
  const [account, setAccount] = useState("");
  const [kind, setKind] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const accounts = useAccounts(false);
  const { start, end } = monthBounds(month);
  const params = new URLSearchParams({ inicio: start, fim: end, limite: "200" });
  if (account) params.set("conta", account);
  if (kind) params.set("tipo", kind);
  if (query) params.set("busca", query);
  const list = useApi<Page>(`/lancamentos?${params.toString()}`);

  const totals = list.state === "ready"
    ? list.data.items.reduce(
        (acc, t) => {
          if (t.kind === "receita") acc.inc += t.amount_cents;
          if (t.kind === "despesa") acc.out += t.amount_cents;
          return acc;
        },
        { inc: 0, out: 0 },
      )
    : null;

  return (
    <div className="stack-lg">
      <PageHeader title="Receitas e despesas" subtitle="Tudo o que entrou e saiu das suas contas." />
      <div className="actions">
        <Link className="btn" href="/lancamentos/novo/?tipo=despesa">+ Registrar despesa</Link>
        <Link className="btn secondary" href="/lancamentos/novo/?tipo=receita">+ Registrar receita</Link>
        <Link className="btn secondary" href="/lancamentos/novo/?tipo=transferencia">Transferir</Link>
      </div>

      <div className="between" role="group" aria-label="Escolher o mês">
        <button type="button" className="btn secondary" onClick={() => setMonth(shiftMonth(month, -1))} aria-label="Mês anterior">← Anterior</button>
        <h2 aria-live="polite">{monthLabel(month)}</h2>
        <button type="button" className="btn secondary" onClick={() => setMonth(shiftMonth(month, 1))} aria-label="Próximo mês">Próximo →</button>
      </div>

      <details className="card more">
        <summary>Filtrar e pesquisar</summary>
        <form className="stack" style={{ marginTop: 8 }} onSubmit={(e) => { e.preventDefault(); setQuery(search.trim()); }}>
          <Select label="Conta" value={account} onChange={setAccount} options={accounts.options} placeholder="Todas as contas" />
          <Select label="Tipo" value={kind} onChange={setKind} placeholder="Todos os tipos"
            options={Object.entries(TX_KINDS).map(([value, label]) => ({ value, label }))} />
          <div className="field">
            <label htmlFor="busca">Pesquisar pela descrição</label>
            <input id="busca" className="input" value={search} maxLength={60} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <button type="submit" className="btn secondary">Pesquisar</button>
        </form>
      </details>

      {totals ? (
        <div className="grid-2">
          <div className="card soft"><p className="stat-label">Receitas no mês</p><p className="stat-value md"><Money cents={totals.inc} /></p></div>
          <div className="card soft"><p className="stat-label">Despesas pagas em conta</p><p className="stat-value md"><Money cents={totals.out} /></p>
            <p className="stat-help">Compras no cartão aparecem em Cartões e no Início.</p></div>
        </div>
      ) : null}

      {list.state === "loading" ? <Loading /> : list.state === "error" ? (
        <ErrorBox message={list.message} onRetry={list.reload} />
      ) : list.data.items.length === 0 ? (
        <Empty title="Nenhum lançamento neste mês">
          Registre uma despesa ou receita com os botões acima. Use as setas para ver outros meses.
        </Empty>
      ) : (
        <ul className="list" aria-label="Lançamentos">
          {list.data.items.map((t) => (
            <li key={t.id}>
              <Link className="list-row" href={`/lancamentos/detalhe/?id=${t.id}`}>
                <span className="main">
                  <span className="title">{t.description}</span>
                  <span className="sub">
                    <DateText iso={t.tx_date} /> · {t.account_name}
                    {t.kind === "transferencia" && t.transfer_other_account_name
                      ? ` ${t.direction === "saida" ? "→" : "←"} ${t.transfer_other_account_name}` : ""}
                    {t.category_name ? ` · ${t.category_name}` : ""} · {TX_KINDS[t.kind] ?? t.kind}
                  </span>
                </span>
                <Money cents={t.direction === "entrada" ? t.amount_cents : -t.amount_cents} signed className="amount" />
              </Link>
            </li>
          ))}
        </ul>
      )}
      {list.state === "ready" && list.data.total > list.data.items.length ? (
        <p className="small muted">Mostrando {list.data.items.length} de {list.data.total}. Use o filtro para encontrar outros.</p>
      ) : null}
      {list.state === "ready" && list.data.items.some((t) => t.status === "cancelado") ? <Badge>Inclui cancelados</Badge> : null}
    </div>
  );
}
