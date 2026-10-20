"use client";

import Link from "next/link";

import { Badge, Empty, ErrorBox, Loading, Money, PageHeader, Stat } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import { ACCOUNT_KINDS } from "@/lib/options";
import type { Account } from "@/lib/types";

export default function AccountsPage() {
  const list = useApi<Account[]>("/contas");
  if (list.state === "loading") return <Loading />;
  if (list.state === "error") return <ErrorBox message={list.message} onRetry={list.reload} />;
  const active = list.data.filter((a) => a.is_active);
  const available = active.filter((a) => a.daily_use).reduce((s, a) => s + a.balance_cents, 0);
  const total = active.reduce((s, a) => s + a.balance_cents, 0);

  return (
    <div className="stack-lg">
      <PageHeader title="Contas" subtitle="O dinheiro que você tem em bancos e em espécie."
        action={<Link className="btn" href="/contas/nova/">+ Nova conta</Link>} />
      {list.data.length === 0 ? (
        <Empty title="Nenhuma conta cadastrada" action={<Link className="btn" href="/contas/nova/">Cadastrar a primeira conta</Link>}>
          Cadastre sua conta do banco, a poupança ou o dinheiro que fica na carteira. Informe quanto há hoje em cada uma.
        </Empty>
      ) : (
        <>
          <div className="card grid-2">
            <Stat label="Dinheiro disponível" cents={available} help="Contas do dia a dia." />
            <Stat size="md" label="Total em todas as contas" cents={total} />
          </div>
          <ul className="list" aria-label="Suas contas">
            {list.data.map((a) => (
              <li key={a.id}>
                <Link className="list-row" href={`/contas/detalhe/?id=${a.id}`}>
                  <span className="main">
                    <span className="title">{a.name}</span>
                    <span className="sub">
                      {ACCOUNT_KINDS[a.kind]}{a.institution ? ` · ${a.institution}` : ""}
                      {!a.daily_use ? " · fora do dinheiro disponível" : ""}
                    </span>
                    {!a.is_active ? <Badge>Desativada</Badge> : null}
                  </span>
                  <Money cents={a.balance_cents} className="amount" />
                </Link>
              </li>
            ))}
          </ul>
          <Link className="btn secondary" href="/lancamentos/novo/?tipo=transferencia">Transferir entre contas</Link>
        </>
      )}
    </div>
  );
}
