"use client";

import { useState } from "react";

import { useShell } from "@/components/Shell";
import { Badge, BackLink, ConfirmButton, ErrorBox, FormError, Loading, MoneyInput, PageHeader, Progress } from "@/components/ui";
import { api } from "@/lib/api";
import { monthLabel } from "@/lib/dates";
import { formatCents } from "@/lib/format";
import { useApi } from "@/lib/hooks";

type Item = {
  category_id: string;
  category_name: string;
  limit_cents: number | null;
  spent_cents: number;
  percent: number | null;
  level: "ok" | "perto" | "passou" | null;
  left_cents: number | null;
  suggested_cents: number | null;
};
type Budgets = { month: string; items: Item[]; notes: string[] };

function Editor({ item, onDone }: { item: Item; onDone: () => void }) {
  const { online, flash } = useShell();
  const [value, setValue] = useState<number | null>(item.limit_cents ?? item.suggested_cents);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    if (!value) return setError("Informe o teto do mês.");
    setBusy(true);
    setError(null);
    try {
      await api.put(`/tetos/${item.category_id}`, { monthly_limit_cents: value });
      flash(`Teto de ${item.category_name} salvo.`);
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="stack" style={{ marginTop: 8 }}>
      <FormError error={error} />
      <MoneyInput label={`Teto por mês para ${item.category_name}`} cents={value} onChange={setValue}
        hint={item.suggested_cents ? <>Sugestão: {formatCents(item.suggested_cents)}, o que você costuma gastar (mediana dos últimos 6 meses).</> : "Quanto quer gastar no máximo por mês."} />
      <button type="button" className="btn" onClick={save} disabled={busy || !online}>{busy ? "Salvando…" : "Salvar teto"}</button>
    </div>
  );
}

function Row({ item, reload }: { item: Item; reload: () => void }) {
  const { online, flash } = useShell();
  const [editing, setEditing] = useState(false);
  const remove = async () => {
    await api.delete(`/tetos/${item.category_id}`);
    flash(`Teto de ${item.category_name} removido.`);
    reload();
  };
  const tone = item.level === "passou" ? "neg" : item.level === "perto" ? "warn" : undefined;
  return (
    <li className="card stack">
      <div className="between">
        <h3 style={{ margin: 0 }}>{item.category_name}</h3>
        {item.level === "passou" ? <Badge tone="neg">Passou do teto</Badge> : item.level === "perto" ? <Badge tone="warn">Perto do teto</Badge> : null}
      </div>
      {item.limit_cents ? (
        <>
          <Progress caption={null} percent={item.percent ?? 0} label={`${item.category_name}: ${item.percent}% do teto`} />
          <p className={tone === "neg" ? "neg" : undefined}>
            <strong>{formatCents(item.spent_cents)}</strong> de {formatCents(item.limit_cents)} ({item.percent}%).{" "}
            {(item.left_cents ?? 0) >= 0 ? <>Ainda pode gastar {formatCents(item.left_cents ?? 0)}.</> : <>Passou {formatCents(-(item.left_cents ?? 0))}.</>}
          </p>
        </>
      ) : (
        <p className="muted">
          Sem teto. Gasto neste mês: {formatCents(item.spent_cents)}.
          {item.suggested_cents ? <> Você costuma gastar cerca de {formatCents(item.suggested_cents)}.</> : null}
        </p>
      )}
      {editing ? <Editor item={item} onDone={() => { setEditing(false); reload(); }} /> : (
        <div className="row">
          <button type="button" className="btn secondary" onClick={() => setEditing(true)} disabled={!online}>
            {item.limit_cents ? "Mudar teto" : "Definir teto"}
          </button>
          {item.limit_cents ? (
            <ConfirmButton label="Tirar teto" title={`Tirar o teto de ${item.category_name}?`} tone="secondary"
              message="A categoria continua nos relatórios, só sem o aviso de teto." confirmLabel="Tirar teto"
              onConfirm={remove} disabled={!online} />
          ) : null}
        </div>
      )}
    </li>
  );
}

export default function BudgetsPage() {
  const budgets = useApi<Budgets>("/tetos");
  if (budgets.state === "loading") return <Loading />;
  if (budgets.state === "error") return <ErrorBox message={budgets.message} onRetry={budgets.reload} />;
  const b = budgets.data;
  const withLimit = b.items.filter((i) => i.limit_cents);
  const without = b.items.filter((i) => !i.limit_cents);
  const [mm, yyyy] = b.month.split("/");
  return (
    <div className="stack-lg">
      <BackLink href="/planejamento/">Planejamento</BackLink>
      <PageHeader title="Teto de gastos"
        subtitle={<>Quanto quer gastar no máximo, por categoria, em {monthLabel(`${yyyy}-${mm}`).toLowerCase()}. O Início avisa quando chegar perto (80%) e quando passar.</>} />
      {withLimit.length > 0 ? (
        <section className="stack" aria-labelledby="com-teto">
          <h2 id="com-teto">Com teto</h2>
          <ul className="stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {withLimit.map((i) => <Row key={i.category_id} item={i} reload={budgets.reload} />)}
          </ul>
        </section>
      ) : null}
      <section className="stack" aria-labelledby="sem-teto">
        <h2 id="sem-teto">{withLimit.length > 0 ? "Sem teto" : "Escolha as categorias"}</h2>
        <ul className="stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {without.map((i) => <Row key={i.category_id} item={i} reload={budgets.reload} />)}
        </ul>
      </section>
      <ul className="small muted" style={{ margin: 0, paddingLeft: 20 }}>{b.notes.map((n) => <li key={n}>{n}</li>)}</ul>
    </div>
  );
}
