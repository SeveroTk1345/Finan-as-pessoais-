"use client";

import { useEffect, useState } from "react";

import { BackLink, ErrorBox, Loading, Money, MoneyInput, Notice, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { formatCents } from "@/lib/format";

type Result = {
  strategy: string;
  label: string;
  order: string[];
  months: number | null;
  total_paid_cents: number;
  total_interest_cents: number;
  warnings: string[];
};
type Response = {
  debts: { id: string; creditor: string; balance_cents: number; has_rate: boolean; has_installment: boolean }[];
  results: Result[];
  warnings: string[];
};

const EXPLAIN: Record<string, string> = {
  maior_juros: "Paga primeiro a dívida com a maior taxa. Costuma gastar menos com juros, se as taxas informadas estiverem corretas.",
  menor_saldo: "Paga primeiro a menor dívida. Você vê dívidas acabando mais cedo, o que ajuda a manter o ânimo.",
  menor_parcela: "Paga primeiro a dívida que acaba mais rápido e libera essa parcela do orçamento mensal.",
  equilibrada: "Mistura juros e quanto a dívida pesa no mês.",
};

function years(months: number): string {
  const y = Math.floor(months / 12);
  const m = months % 12;
  return [y ? `${y} ano${y > 1 ? "s" : ""}` : "", m ? `${m} ${m > 1 ? "meses" : "mês"}` : ""].filter(Boolean).join(" e ");
}

export default function StrategiesPage() {
  const [extra, setExtra] = useState<number | null>(null);
  const [data, setData] = useState<Response | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const t = setTimeout(() => {
      api.post<Response>("/dividas/estrategias", { extra_monthly_cents: extra ?? 0 })
        .then((r) => alive && setData(r))
        .catch((e: unknown) => alive && setError(e instanceof Error ? e.message : "Erro."));
    }, 300);
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, [extra]);

  const names = Object.fromEntries((data?.debts ?? []).map((d) => [d.id, d.creditor]));
  const best = data?.results.filter((r) => r.months !== null).sort((a, b) => a.total_interest_cents - b.total_interest_cents)[0];

  return (
    <div className="stack-lg">
      <BackLink href="/dividas/">Dívidas</BackLink>
      <PageHeader title="Qual dívida pagar primeiro?" subtitle="Simulação com os dados que você registrou. Não é uma promessa de resultado." />
      <MoneyInput label="Quanto a mais você consegue pagar por mês, além das parcelas?" cents={extra} onChange={setExtra} allowZero
        hint="Pode deixar em branco para ver só com as parcelas atuais." />
      {error ? <ErrorBox message={error} /> : !data ? <Loading /> : data.results.length === 0 ? (
        <Notice>{data.warnings[0]}</Notice>
      ) : (
        <>
          {data.debts.some((d) => !d.has_rate) ? (
            <Notice tone="warn" title="Informação incompleta">
              Algumas dívidas estão sem taxa de juros. A comparação considera só os juros que você informou.
            </Notice>
          ) : null}
          {data.results.map((r) => (
            <section key={r.strategy} className="card stack" aria-label={r.label}>
              <div className="between"><h2>{r.label}</h2>{best && best.strategy === r.strategy ? <span className="badge pos">Menos juros</span> : null}</div>
              <p className="muted">{EXPLAIN[r.strategy]}</p>
              {r.months === null ? (
                <p className="neg">{r.warnings[r.warnings.length - 1]}</p>
              ) : (
                <>
                  <p>Quita tudo em cerca de <strong>{years(r.months)}</strong>.</p>
                  <p>Juros estimados: <strong><Money cents={r.total_interest_cents} /></strong> · total pago {formatCents(r.total_paid_cents)}</p>
                </>
              )}
              <ol style={{ margin: 0, paddingLeft: 22 }}>
                {r.order.map((id) => <li key={id}>{names[id] ?? id}</li>)}
              </ol>
            </section>
          ))}
          <p className="small muted">{data.warnings.join(" ")}</p>
        </>
      )}
    </div>
  );
}
