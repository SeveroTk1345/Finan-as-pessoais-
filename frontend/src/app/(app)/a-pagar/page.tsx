"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { useShell } from "@/components/Shell";
import { Badge, DateText, Empty, ErrorBox, Loading, Money, PageHeader, Situation } from "@/components/ui";
import { api, newOperationKey } from "@/lib/api";
import { monthBounds, monthLabel, monthOf, shiftMonth, todayInSaoPaulo } from "@/lib/dates";
import { formatCents } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { billTitle, type Bill, type Obligation } from "@/lib/types";

type Tab = "pagar" | "receber";

function OpenBill({ bill, children }: { bill: Bill; children: React.ReactNode }) {
  const router = useRouter();
  const { flash } = useShell();
  const [busy, setBusy] = useState(false);
  if (bill.id) {
    return <Link className="list-row" href={`/a-pagar/detalhe/?id=${bill.id}`}>{children}</Link>;
  }
  // Ocorrência de recorrência ainda não gravada: grava ao abrir para pagar.
  return (
    <button type="button" className="list-row" disabled={busy}
      style={{ width: "100%", background: "none", border: "none", font: "inherit", textAlign: "left", cursor: "pointer" }}
      onClick={async () => {
        setBusy(true);
        try {
          const b = await api.create<Bill>("/contas-a-pagar/ocorrencia",
            { rule_id: bill.rule_id, occurrence_date: bill.occurrence_date }, newOperationKey());
          router.push(`/a-pagar/detalhe/?id=${b.id}`);
        } catch (e) {
          flash(e instanceof Error ? e.message : "Erro ao abrir.");
          setBusy(false);
        }
      }}>
      {children}
    </button>
  );
}

const OBL_LINK = (o: Obligation) =>
  o.source === "fatura" ? `/cartoes/fatura/?id=${o.id}&venc=${o.due_date}` : o.source === "divida" ? `/dividas/detalhe/?id=${o.id}` : null;

export default function BillsPage() {
  const [tab, setTab] = useState<Tab>("pagar");
  const [month, setMonth] = useState(monthOf(todayInSaoPaulo()));
  const { start, end } = monthBounds(month);
  const upcoming = useApi<{ items: Obligation[]; total_cents: number }>("/a-pagar?dias=30");
  const bills = useApi<Bill[]>(`/contas-a-pagar?inicio=${start}&fim=${end}&tipo=${tab}`);

  return (
    <div className="stack-lg">
      <PageHeader title="Contas a pagar" subtitle="Compromissos, vencimentos e o que você ainda vai receber."
        action={<Link className="btn" href={`/a-pagar/nova/?tipo=${tab}`}>{tab === "pagar" ? "+ Nova conta a pagar" : "+ Nova receita prevista"}</Link>} />

      <section className="card stack" aria-labelledby="prox">
        <h2 id="prox">Próximos 30 dias</h2>
        {upcoming.state === "loading" ? <Loading /> : upcoming.state === "error" ? (
          <ErrorBox message={upcoming.message} onRetry={upcoming.reload} />
        ) : upcoming.data.items.length === 0 ? (
          <p className="muted">Nada vencendo nos próximos 30 dias.</p>
        ) : (
          <>
            <p>Total: <strong><Money cents={upcoming.data.total_cents} /></strong> (contas, faturas e parcelas, sem repetir nada).</p>
            <ul className="list">
              {upcoming.data.items.filter((o) => o.source !== "conta").map((o, i) => (
                <li key={`${o.source}-${o.id}-${o.due_date}-${i}`}>
                  <Link className="list-row" href={OBL_LINK(o) ?? "/a-pagar/"}>
                    <span className="main">
                      <span className="title">{o.description}</span>
                      <span className="sub">Vence <DateText iso={o.due_date} /> {o.overdue ? <Badge tone="neg">Vencida</Badge> : null}</span>
                    </span>
                    <Money cents={o.amount_cents} className="amount" />
                  </Link>
                </li>
              ))}
            </ul>
            <p className="small muted">Faturas e parcelas de dívidas aparecem aqui para você ver tudo junto. Contas avulsas estão na lista abaixo.</p>
          </>
        )}
      </section>

      <div className="tabs" role="tablist" aria-label="Tipo">
        <button role="tab" aria-selected={tab === "pagar"} onClick={() => setTab("pagar")}>A pagar</button>
        <button role="tab" aria-selected={tab === "receber"} onClick={() => setTab("receber")}>A receber</button>
      </div>

      <div className="between" role="group" aria-label="Escolher o mês">
        <button type="button" className="btn secondary" onClick={() => setMonth(shiftMonth(month, -1))}>← Anterior</button>
        <h2 aria-live="polite">{monthLabel(month)}</h2>
        <button type="button" className="btn secondary" onClick={() => setMonth(shiftMonth(month, 1))}>Próximo →</button>
      </div>

      {bills.state === "loading" ? <Loading /> : bills.state === "error" ? (
        <ErrorBox message={bills.message} onRetry={bills.reload} />
      ) : bills.data.length === 0 ? (
        <Empty title={tab === "pagar" ? "Nenhuma conta neste mês" : "Nenhuma receita prevista neste mês"}
          action={<Link className="btn secondary" href={`/a-pagar/nova/?tipo=${tab}`}>Cadastrar</Link>}>
          {tab === "pagar"
            ? "Cadastre aluguel, luz, água e outras contas. Contas que se repetem todo mês podem ser cadastradas uma vez só."
            : "Cadastre salário, aposentadoria ou outro valor que você espera receber."}
        </Empty>
      ) : (
        <>
          <p className="muted">
            {tab === "pagar" ? "Falta pagar" : "Falta receber"}:{" "}
            <strong>{formatCents(bills.data.reduce((s, b) => s + b.remaining_cents, 0))}</strong>
          </p>
          <ul className="list" aria-label="Contas do mês">
            {bills.data.map((b) => (
              <li key={b.id ?? `${b.rule_id}-${b.due_date}`}>
                <OpenBill bill={b}>
                  <span className="main">
                    <span className="title">{billTitle(b)}</span>
                    <span className="sub">
                      Vence <DateText iso={b.due_date} />{b.category_name ? ` · ${b.category_name}` : ""}
                      {b.rule_id ? " · repete" : ""}
                    </span>
                    <span className="row" style={{ gap: 6, marginTop: 4 }}>
                      <Situation value={b.situation} receiving={tab === "receber"} />
                      {b.due_soon ? <Badge tone="warn">Vence em breve</Badge> : null}
                    </span>
                  </span>
                  <span style={{ textAlign: "right" }}>
                    <Money cents={b.amount_cents} className="amount" />
                    {b.paid_cents > 0 && b.remaining_cents > 0 ? (
                      <span className="sub small" style={{ display: "block" }}>falta {formatCents(b.remaining_cents)}</span>
                    ) : null}
                  </span>
                </OpenBill>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
