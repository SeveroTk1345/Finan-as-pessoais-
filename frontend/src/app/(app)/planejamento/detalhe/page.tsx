"use client";

import { useSearchParams } from "next/navigation";
import { type FormEvent, Suspense, useState } from "react";

import { useShell } from "@/components/Shell";
import {
  BackLink, ConfirmButton, DateText, ErrorBox, FormError, Loading, Money, MoneyInput, Notice, PageHeader, Progress, Segmented, Stat, SubmitButton,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useApi, useSubmit } from "@/lib/hooks";
import type { Goal } from "@/lib/types";

function Contribute({ goal, onDone }: { goal: Goal; onDone: () => void }) {
  const { online, flash } = useShell();
  const submit = useSubmit();
  const [direction, setDirection] = useState<"deposito" | "retirada">("deposito");
  const [amount, setAmount] = useState<number | null>(null);
  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const ok = await submit.run((key) => api.create(`/metas/${goal.id}/contribuicoes`, { direction, amount_cents: amount }, key));
    if (ok) {
      flash(direction === "deposito" ? "Valor guardado na meta." : "Retirada registrada.");
      setAmount(null);
      onDone();
    }
  };
  return (
    <form className="card stack" onSubmit={onSubmit} noValidate>
      <h2>Guardar ou retirar</h2>
      <p className="small muted">Registre aqui quanto você separou para esta meta. Isso não movimenta suas contas.</p>
      <FormError error={submit.error} />
      <Segmented label="Operação" value={direction} onChange={setDirection}
        options={[{ value: "deposito", label: "Guardei" }, { value: "retirada", label: "Retirei" }]} />
      <MoneyInput label="Valor" cents={amount} onChange={setAmount} error={submit.fields.amount_cents} />
      <SubmitButton busy={submit.busy} online={online}>Registrar</SubmitButton>
    </form>
  );
}

function Detail({ id }: { id: string }) {
  const { online, flash } = useShell();
  const goal = useApi<Goal>(`/metas/${id}`);
  const [error, setError] = useState<string | null>(null);
  if (goal.state === "loading") return <Loading />;
  if (goal.state === "error") return <ErrorBox message={goal.message} onRetry={goal.reload} />;
  const g = goal.data;
  return (
    <div className="stack-lg">
      <BackLink href="/planejamento/">Planejamento</BackLink>
      <PageHeader title={g.name} subtitle={g.kind_label} />
      <div className="card stack">
        <Stat label="Guardado até agora" cents={g.accumulated_cents} help={<>Meta: <Money cents={g.target_cents} /></>} />
        <Progress percent={g.percent} label="Progresso da meta" />
        {g.missing_cents > 0 ? <p>Faltam <strong><Money cents={g.missing_cents} /></strong>.</p> : <p className="pos"><strong>Meta atingida!</strong></p>}
        {g.months_needed && g.missing_cents > 0 ? (
          <p>Mantendo o depósito planejado, faltam cerca de <strong>{g.months_needed} meses</strong>
            {g.projected_date ? <> (por volta de <DateText iso={g.projected_date} />)</> : null}.</p>
        ) : null}
        {g.on_track === false && g.target_date ? (
          <Notice tone="warn">No ritmo planejado, a meta não fica pronta até <DateText iso={g.target_date} />.</Notice>
        ) : null}
        <p className="small muted">{g.assumption}</p>
      </div>
      <FormError error={error} />
      {g.is_active ? <Contribute goal={g} onDone={goal.reload} /> : null}
      {(g.contributions ?? []).length > 0 ? (
        <section className="stack">
          <h2>Histórico</h2>
          <ul className="list">
            {(g.contributions ?? []).map((c) => (
              <li key={c.id} className="list-row">
                <span className="main"><span className="title">{c.direction === "deposito" ? "Guardei" : "Retirei"}</span>
                  <span className="sub"><DateText iso={c.contribution_date} />{c.note ? ` · ${c.note}` : ""}</span></span>
                <span className="row">
                  <Money cents={c.direction === "deposito" ? c.amount_cents : -c.amount_cents} signed className="amount" />
                  <ConfirmButton label="Excluir" tone="secondary" title="Excluir este registro?" confirmLabel="Excluir" disabled={!online}
                    message={<p>O valor deixa de contar na meta.</p>}
                    onConfirm={async () => {
                      try {
                        await api.delete(`/metas/contribuicoes/${c.id}`);
                        flash("Registro excluído.");
                        goal.reload();
                      } catch (e) {
                        setError(e instanceof Error ? e.message : "Erro.");
                      }
                    }} />
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <ConfirmButton tone="secondary" label={g.is_active ? "Arquivar meta" : "Reativar meta"} disabled={!online}
        title={g.is_active ? "Arquivar esta meta?" : "Reativar esta meta?"} confirmLabel={g.is_active ? "Arquivar" : "Reativar"}
        message={<p>O histórico continua guardado.</p>}
        onConfirm={async () => {
          await api.patch(`/metas/${id}`, { is_active: !g.is_active, version: g.version });
          flash(g.is_active ? "Meta arquivada." : "Meta reativada.");
          goal.reload();
        }} />
    </div>
  );
}

function Inner() {
  const id = useSearchParams().get("id");
  if (!id) return <ErrorBox message="Meta não informada." />;
  return <Detail id={id} />;
}

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <Inner />
    </Suspense>
  );
}
