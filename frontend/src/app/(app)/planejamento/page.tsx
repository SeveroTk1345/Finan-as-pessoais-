"use client";

import Link from "next/link";

import { Badge, DateText, Empty, ErrorBox, Loading, Money, PageHeader, Progress } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import type { Goal } from "@/lib/types";

export default function PlanningPage() {
  const goals = useApi<Goal[]>("/metas");
  if (goals.state === "loading") return <Loading />;
  if (goals.state === "error") return <ErrorBox message={goals.message} onRetry={goals.reload} />;
  return (
    <div className="stack-lg">
      <PageHeader title="Planejamento" subtitle="Seus objetivos e quanto falta para chegar lá."
        action={<Link className="btn" href="/planejamento/nova/">+ Nova meta</Link>} />
      <Link href="/planejamento/posso-comprar/" className="card card-link stack">
        <h2>Posso comprar?</h2>
        <p className="muted">Simule uma compra à vista ou parcelada e veja como ficam os próximos meses.</p>
      </Link>
      {goals.data.length === 0 ? (
        <Empty title="Nenhuma meta ainda" action={<Link className="btn" href="/planejamento/nova/">Criar meta</Link>}>
          Crie uma meta como reserva de emergência, viagem ou troca de carro. Você registra quanto guardou e o app mostra o progresso.
        </Empty>
      ) : (
        <div className="stack">
          {goals.data.map((g) => (
            <Link key={g.id} href={`/planejamento/detalhe/?id=${g.id}`} className="card card-link stack">
              <div className="between">
                <h2>{g.name}</h2>
                {g.percent >= 100 ? <Badge tone="pos">Meta atingida</Badge> : g.on_track === false ? <Badge tone="warn">Abaixo do ritmo</Badge> : null}
              </div>
              <p>
                <Money cents={g.accumulated_cents} /> de <Money cents={g.target_cents} />
                {g.target_date ? <> até <DateText iso={g.target_date} /></> : null}
              </p>
              <Progress percent={g.percent} label={`Progresso da meta ${g.name}`} />
              {g.missing_cents > 0 ? (
                <p className="small muted">
                  Faltam <Money cents={g.missing_cents} />.
                  {g.projected_date ? <> Com o depósito planejado, você chega lá por volta de <DateText iso={g.projected_date} /> (estimativa).</> : null}
                </p>
              ) : null}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
