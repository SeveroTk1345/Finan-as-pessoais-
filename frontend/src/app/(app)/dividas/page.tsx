"use client";

import Link from "next/link";

import { Badge, DateText, Empty, ErrorBox, Loading, Money, PageHeader, Stat } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import { DEBT_KINDS } from "@/lib/options";
import type { Card, Debt } from "@/lib/types";


export default function DebtsPage() {
  const debts = useApi<Debt[]>("/dividas");
  const cards = useApi<Card[]>("/cartoes");
  if (debts.state === "loading") return <Loading />;
  if (debts.state === "error") return <ErrorBox message={debts.message} onRetry={debts.reload} />;
  const active = debts.data.filter((d) => d.status === "ativa");
  const closed = debts.data.filter((d) => d.status !== "ativa");
  const direct = active.filter((d) => !d.is_card_channel).reduce((s, d) => s + d.balance_cents, 0);
  const cardsOutstanding = cards.state === "ready" ? cards.data.reduce((s, c) => s + c.outstanding_cents, 0) : 0;

  return (
    <div className="stack-lg">
      <PageHeader title="Dívidas e parcelas" subtitle="Tudo o que você ainda precisa pagar."
        action={<Link className="btn" href="/dividas/nova/">+ Nova dívida</Link>} />
      <div className="card grid-2">
        <Stat label="Faltam para quitar as dívidas" cents={direct} help="Conforme os dados registrados." />
        <Stat size="md" label="Faltam nos cartões (faturas e parcelas)" cents={cardsOutstanding}
          help={<Link href="/cartoes/">Ver cartões</Link>} />
      </div>
      {active.length > 1 ? <Link className="btn secondary" href="/dividas/estrategias/">Qual dívida pagar primeiro?</Link> : null}
      {debts.data.length === 0 ? (
        <Empty title="Nenhuma dívida cadastrada" action={<Link className="btn" href="/dividas/nova/">Cadastrar dívida</Link>}>
          Cadastre empréstimos, financiamentos e outras dívidas para acompanhar quanto falta e quando vence cada parcela. Compras
          parceladas no cartão ficam em Cartões.
        </Empty>
      ) : (
        <ul className="list" aria-label="Dívidas ativas">
          {active.map((d) => (
            <li key={d.id}>
              <Link className="list-row" href={`/dividas/detalhe/?id=${d.id}`}>
                <span className="main">
                  <span className="title">{d.creditor}</span>
                  <span className="sub">
                    {DEBT_KINDS[d.kind] ?? d.kind}
                    {d.installments_total ? ` · ${d.installments_paid} de ${d.installments_total} parcelas pagas` : ""}
                  </span>
                  <span className="row" style={{ gap: 6, marginTop: 4 }}>
                    {d.next_due_date ? <span className="small">Próxima: <DateText iso={d.next_due_date} /></span> : null}
                    {d.overdue ? <Badge tone="neg">Parcela atrasada</Badge> : null}
                    {d.balance_estimated ? <Badge tone="warn">Saldo estimado</Badge> : null}
                  </span>
                </span>
                <Money cents={d.balance_cents} className="amount" />
              </Link>
            </li>
          ))}
        </ul>
      )}
      {closed.length > 0 ? (
        <details className="card more">
          <summary>Quitadas, renegociadas e canceladas ({closed.length})</summary>
          <ul className="list" style={{ marginTop: 8 }}>
            {closed.map((d) => (
              <li key={d.id}>
                <Link className="list-row" href={`/dividas/detalhe/?id=${d.id}`}>
                  <span className="main"><span className="title">{d.creditor}</span>
                    <span className="sub">{d.status === "quitada" ? "Quitada" : d.status === "renegociada" ? "Renegociada" : "Cancelada"}</span></span>
                  <Money cents={d.original_amount_cents} className="amount" />
                </Link>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}
