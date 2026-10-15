"use client";

import Link from "next/link";

import { Badge, DateText, Empty, ErrorBox, Loading, Money, PageHeader } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import type { Card } from "@/lib/types";

export default function CardsPage() {
  const cards = useApi<Card[]>("/cartoes");
  if (cards.state === "loading") return <Loading />;
  if (cards.state === "error") return <ErrorBox message={cards.message} onRetry={cards.reload} />;
  return (
    <div className="stack-lg">
      <PageHeader title="Cartões de crédito" subtitle="Faturas, limite e compras parceladas."
        action={<Link className="btn" href="/cartoes/novo/">+ Novo cartão</Link>} />
      <p className="small muted">O limite do cartão não é dinheiro seu: ele nunca entra no dinheiro disponível.</p>
      {cards.data.length === 0 ? (
        <Empty title="Nenhum cartão cadastrado" action={<Link className="btn" href="/cartoes/novo/">Cadastrar cartão</Link>}>
          Cadastre seu cartão com o limite e os dias de fechamento e de vencimento da fatura.
        </Empty>
      ) : (
        <div className="stack">
          {cards.data.map((c) => (
            <Link key={c.id} href={`/cartoes/detalhe/?id=${c.id}`} className="card card-link stack">
              <div className="between">
                <h2>{c.name}</h2>
                {!c.is_active ? <Badge>Desativado</Badge> : null}
              </div>
              <div className="grid-2">
                <div>
                  <p className="stat-label">Fatura aberta (vence <DateText iso={c.open_invoice.due_date} />)</p>
                  <p className="stat-value md"><Money cents={c.open_invoice.total_cents} /></p>
                </div>
                <div>
                  <p className="stat-label">Limite disponível</p>
                  <p className="stat-value md"><Money cents={c.limit_available_cents} /></p>
                  <p className="stat-help">de <Money cents={c.limit_cents} /> no total</p>
                </div>
              </div>
              {c.invoices_to_pay.length > 0 ? (
                <p className="neg">
                  {c.invoices_to_pay.length} fatura(s) fechada(s) com valor a pagar:{" "}
                  <Money cents={c.invoices_to_pay.reduce((s, i) => s + i.remaining_cents, 0)} />
                </p>
              ) : null}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
