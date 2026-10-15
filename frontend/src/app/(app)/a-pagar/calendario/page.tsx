"use client";

import Link from "next/link";
import { useState } from "react";

import { Badge, BackLink, DateText, ErrorBox, Loading, Money, PageHeader } from "@/components/ui";
import { monthBounds, monthLabel, monthOf, shiftMonth, todayInSaoPaulo, weekdayIso } from "@/lib/dates";
import { formatCents } from "@/lib/format";
import { useApi } from "@/lib/hooks";

type Item = {
  date: string;
  kind: "pagar" | "receber";
  source: "conta" | "fatura" | "divida";
  id: string | null;
  rule_id?: string | null;
  virtual?: boolean;
  description: string;
  amount_cents: number;
  situation: string;
};
type Calendar = { month: string; today: string; items: Item[]; to_pay_cents: number; to_receive_cents: number };

const WEEKDAYS = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
const WEEKDAY_NAMES = ["domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado"];

function itemLink(i: Item): string {
  if (i.source === "fatura") return `/cartoes/fatura/?id=${i.id}&venc=${i.date}`;
  if (i.source === "divida") return `/dividas/detalhe/?id=${i.id}`;
  return i.id && !i.virtual ? `/a-pagar/detalhe/?id=${i.id}` : "/a-pagar/";
}

function situationBadge(i: Item) {
  if (i.situation === "paga") return <Badge tone="pos">{i.kind === "receber" ? "Recebida" : "Paga"}</Badge>;
  if (i.situation === "vencida") return <Badge tone="neg">Vencida</Badge>;
  return <Badge>{i.kind === "receber" ? "A receber" : "A pagar"}</Badge>;
}

function MonthGrid({ month, data }: { month: string; data: Calendar }) {
  const { start, end } = monthBounds(month);
  const lastDay = Number(end.slice(8, 10));
  const offset = weekdayIso(start);
  const byDay = new Map<string, Item[]>();
  for (const i of data.items) byDay.set(i.date, [...(byDay.get(i.date) ?? []), i]);
  const firstWithItems = data.items[0]?.date;
  const initial = data.today.startsWith(month) ? data.today : firstWithItems ?? start;
  const [selected, setSelected] = useState(initial);
  const days = Array.from({ length: lastDay }, (_, k) => `${month}-${String(k + 1).padStart(2, "0")}`);
  const chosen = byDay.get(selected) ?? [];

  return (
    <>
      <div className="calendar" role="group" aria-label={`Calendário de ${monthLabel(month).toLowerCase()}`}>
        {WEEKDAYS.map((w) => <span key={w} className="cal-head" aria-hidden="true">{w}</span>)}
        {Array.from({ length: offset }, (_, k) => <span key={`v${k}`} aria-hidden="true" />)}
        {days.map((iso) => {
          const items = byDay.get(iso) ?? [];
          const pay = items.filter((i) => i.kind === "pagar").reduce((s, i) => s + i.amount_cents, 0);
          const receive = items.some((i) => i.kind === "receber");
          const late = items.some((i) => i.situation === "vencida");
          const day = Number(iso.slice(8, 10));
          const label = `${day} de ${monthLabel(month).toLowerCase().split(" de ")[0]}, ${WEEKDAY_NAMES[weekdayIso(iso)]}: `
            + (items.length ? `${items.length} ${items.length === 1 ? "item" : "itens"}${pay ? `, ${formatCents(pay)} a pagar` : ""}` : "nada");
          return (
            <button key={iso} type="button" aria-pressed={iso === selected} aria-label={label}
              className={["cal-day", iso === data.today ? "today" : "", items.length ? "has" : "", late ? "late" : ""].join(" ")}
              onClick={() => setSelected(iso)}>
              <span className="cal-num">{day}</span>
              {pay ? <span className="cal-amount">{formatCents(pay).replace("R$ ", "")}</span> : null}
              <span className="cal-marks" aria-hidden="true">{pay ? "●" : ""}{receive ? "+" : ""}</span>
            </button>
          );
        })}
      </div>
      <p className="small muted">● tem conta a pagar · + tem dinheiro a receber · borda grossa: hoje · vermelho: vencida.</p>

      <section className="stack" aria-live="polite" aria-labelledby="dia">
        <h2 id="dia"><DateText iso={selected} /> ({WEEKDAY_NAMES[weekdayIso(selected)]})</h2>
        {chosen.length === 0 ? <p className="muted">Nada vence neste dia.</p> : (
          <ul className="list">
            {chosen.map((i, k) => (
              <li key={`${i.source}-${i.id ?? i.rule_id}-${k}`}>
                <Link className="list-row" href={itemLink(i)}>
                  <span className="main">
                    <span className="title">{i.description}</span>
                    <span className="row" style={{ gap: 6, marginTop: 4 }}>{situationBadge(i)}</span>
                  </span>
                  <Money cents={i.kind === "receber" ? i.amount_cents : -i.amount_cents} className="amount" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}

export default function CalendarPage() {
  const [month, setMonth] = useState(monthOf(todayInSaoPaulo()));
  const cal = useApi<Calendar>(`/calendario?mes=${month}`);
  return (
    <div className="stack-lg">
      <BackLink href="/a-pagar/">Contas a pagar</BackLink>
      <PageHeader title="Calendário de contas" subtitle="O que vence e o que entra em cada dia do mês." />
      <div className="month-nav" role="group" aria-label="Escolher o mês">
        <button type="button" className="btn secondary" aria-label="Mês anterior" onClick={() => setMonth(shiftMonth(month, -1))}><span aria-hidden="true">←</span> <span className="nav-word">Anterior</span></button>
        <h2 aria-live="polite">{monthLabel(month)}</h2>
        <button type="button" className="btn secondary" aria-label="Próximo mês" onClick={() => setMonth(shiftMonth(month, 1))}><span className="nav-word">Próximo</span> <span aria-hidden="true">→</span></button>
      </div>
      {cal.state === "loading" ? <Loading /> : cal.state === "error" ? <ErrorBox message={cal.message} onRetry={cal.reload} /> : (
        <>
          <p>No mês: <strong>{formatCents(cal.data.to_pay_cents)}</strong> a pagar e <strong>{formatCents(cal.data.to_receive_cents)}</strong> a receber.</p>
          <MonthGrid key={month} month={month} data={cal.data} />
        </>
      )}
    </div>
  );
}
