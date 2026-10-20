"use client";

import Link from "next/link";
import { type ReactNode, useEffect, useId, useRef, useState } from "react";

import { digitsToCents, formatCents, formatIsoDate, isValidIsoDate } from "@/lib/format";

// --- texto e valores ------------------------------------------------------------

export function Money({ cents, signed = false, className = "" }: { cents: number | null | undefined; signed?: boolean; className?: string }) {
  if (cents === null || cents === undefined) return <span className={`num muted ${className}`}>—</span>;
  const tone = signed ? (cents < 0 ? "neg" : cents > 0 ? "pos" : "") : "";
  const prefix = signed && cents > 0 ? "+" : "";
  return <span className={`num ${tone} ${className}`}>{prefix + formatCents(cents)}</span>;
}

export function DateText({ iso }: { iso: string | null | undefined }) {
  if (!iso) return <span className="muted">—</span>;
  return <span className="num">{formatIsoDate(iso.slice(0, 10))}</span>;
}

export function PageHeader({ title, subtitle, action }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="between">
      <div className="page-head">
        <h1>{title}</h1>
        {subtitle ? <p className="muted">{subtitle}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function Notice({ tone = "", title, children }: { tone?: "" | "neg" | "pos" | "warn"; title?: string; children?: ReactNode }) {
  return (
    <div className={`notice ${tone}`} role={tone === "neg" ? "alert" : "status"}>
      {title ? <strong>{title}</strong> : null}
      {children}
    </div>
  );
}

export function Loading({ label = "Carregando…" }: { label?: string }) {
  return (
    <div className="stack" aria-busy="true" aria-live="polite">
      <p className="muted">{label}</p>
      <div className="skeleton" style={{ height: 80 }} />
      <div className="skeleton" style={{ height: 80 }} />
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <Notice tone="neg" title="Não foi possível carregar">
      <p>{message}</p>
      {onRetry ? (
        <button type="button" className="btn secondary" style={{ marginTop: 12 }} onClick={onRetry}>
          Tentar de novo
        </button>
      ) : null}
    </Notice>
  );
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="card soft stack" style={{ alignItems: "flex-start" }}>
      <h2>{title}</h2>
      {children ? <p className="muted">{children}</p> : null}
      {action}
    </div>
  );
}

export function Stat({ label, cents, help, signed = false, size = "lg" }: { label: string; cents: number | null; help?: ReactNode; signed?: boolean; size?: "lg" | "md" }) {
  return (
    <div>
      <p className="stat-label">{label}</p>
      <p className={`stat-value ${size === "md" ? "md" : ""}`}>
        <Money cents={cents} signed={signed} />
      </p>
      {help ? <p className="stat-help">{help}</p> : null}
    </div>
  );
}

export function Badge({ tone = "", children }: { tone?: "" | "neg" | "pos" | "warn"; children: ReactNode }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

const SITUATIONS: Record<string, { label: string; tone: "" | "neg" | "pos" | "warn" }> = {
  pendente: { label: "A pagar", tone: "" },
  vencida: { label: "Vencida", tone: "neg" },
  parcialmente_paga: { label: "Paga em parte", tone: "warn" },
  paga: { label: "Paga", tone: "pos" },
  cancelada: { label: "Cancelada", tone: "" },
  futura: { label: "Futura", tone: "" },
  aberta: { label: "Aberta", tone: "" },
  fechada: { label: "Fechada", tone: "warn" },
  com_credito: { label: "Com crédito", tone: "pos" },
};

export function Situation({ value, receiving = false }: { value: string; receiving?: boolean }) {
  const s = SITUATIONS[value] ?? { label: value, tone: "" as const };
  let label = s.label;
  if (receiving) label = value === "paga" ? "Recebida" : value === "pendente" ? "A receber" : value === "vencida" ? "Atrasada" : label;
  return <Badge tone={s.tone}>{label}</Badge>;
}

// --- formulários ------------------------------------------------------------------

type FieldProps = { label: string; hint?: ReactNode; error?: string; children: (id: string, describedBy: string | undefined) => ReactNode };

export function Field({ label, hint, error, children }: FieldProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children(id, describedBy)}
      {hint ? <p className="hint" id={hintId}>{hint}</p> : null}
      {error ? <p className="error" id={errorId}>{error}</p> : null}
    </div>
  );
}

export function TextInput({ label, value, onChange, error, hint, maxLength = 120, required = false, autoComplete, type = "text" }: {
  label: string; value: string; onChange: (v: string) => void; error?: string; hint?: ReactNode; maxLength?: number; required?: boolean; autoComplete?: string; type?: string;
}) {
  return (
    <Field label={label} hint={hint} error={error}>
      {(id, d) => (
        <input id={id} className="input" type={type} value={value} maxLength={maxLength} required={required}
          autoComplete={autoComplete} aria-invalid={error ? true : undefined} aria-describedby={d}
          onChange={(e) => onChange(e.target.value)} />
      )}
    </Field>
  );
}

/** Valor em reais com máscara de centavos: os números entram pela direita. */
export function MoneyInput({ label, cents, onChange, error, hint, allowZero = false }: {
  label: string; cents: number | null; onChange: (c: number | null) => void; error?: string; hint?: ReactNode; allowZero?: boolean;
}) {
  const shown = cents === null ? "" : formatCents(cents);
  return (
    <Field label={label} hint={hint ?? "Digite só os números. Ex.: 1234 vira R$ 12,34."} error={error}>
      {(id, d) => (
        <input id={id} className="input money-input" inputMode="numeric" autoComplete="off" value={shown}
          placeholder="R$ 0,00" aria-invalid={error ? true : undefined} aria-describedby={d}
          onChange={(e) => {
            const digits = e.target.value.replace(/\D/g, "");
            if (digits === "") return onChange(null);
            try {
              const c = digitsToCents(digits);
              onChange(c === 0 && !allowZero ? null : c);
            } catch {
              /* valor alto demais: ignora o dígito extra */
            }
          }} />
      )}
    </Field>
  );
}

export function DateInput({ label, value, onChange, error, hint, max }: {
  label: string; value: string; onChange: (v: string) => void; error?: string; hint?: ReactNode; max?: string;
}) {
  // O seletor de data é o do próprio aparelho; abaixo mostramos sempre DD/MM/AAAA.
  const chosen = value && isValidIsoDate(value) ? `Data escolhida: ${formatIsoDate(value)}.` : null;
  return (
    <Field label={label} hint={chosen || hint ? <>{chosen} {hint}</> : undefined} error={error}>
      {(id, d) => (
        <input id={id} className="input" type="date" value={value} max={max} aria-invalid={error ? true : undefined}
          aria-describedby={d} onChange={(e) => onChange(e.target.value)} />
      )}
    </Field>
  );
}

export function Select({ label, value, onChange, options, error, hint, placeholder }: {
  label: string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; error?: string; hint?: ReactNode; placeholder?: string;
}) {
  return (
    <Field label={label} hint={hint} error={error}>
      {(id, d) => (
        <select id={id} className="input" value={value} aria-invalid={error ? true : undefined} aria-describedby={d}
          onChange={(e) => onChange(e.target.value)}>
          {placeholder !== undefined ? <option value="">{placeholder}</option> : null}
          {options.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      )}
    </Field>
  );
}

export function NumberInput({ label, value, onChange, error, hint, min = 1, max = 999 }: {
  label: string; value: string; onChange: (v: string) => void; error?: string; hint?: ReactNode; min?: number; max?: number;
}) {
  return (
    <Field label={label} hint={hint} error={error}>
      {(id, d) => (
        <input id={id} className="input" inputMode="numeric" value={value} aria-invalid={error ? true : undefined}
          aria-describedby={d} onChange={(e) => {
            const v = e.target.value.replace(/\D/g, "").slice(0, String(max).length);
            onChange(v);
          }} min={min} max={max} />
      )}
    </Field>
  );
}

export function Checkbox({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="check">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

export function Segmented<T extends string>({ label, value, onChange, options }: {
  label: string; value: T; onChange: (v: T) => void; options: { value: T; label: string }[];
}) {
  return (
    <div className="field" role="group" aria-label={label}>
      <span className="label">{label}</span>
      <div className="segmented">
        {options.map((o) => (
          <button key={o.value} type="button" aria-pressed={value === o.value} onClick={() => onChange(o.value)}>
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

/**
 * Escolha em botões grandes ("Com o que foi o gasto?"). Tocar de novo no escolhido
 * desmarca. Cada botão mostra exemplos, para não precisar adivinhar a categoria.
 */
export function CategoryPicker({ label, value, onChange, options, hints = {}, error }: {
  label: string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[];
  hints?: Record<string, string>; error?: string;
}) {
  const errorId = useId();
  return (
    <div className="field" role="group" aria-label={label} aria-describedby={error ? errorId : undefined}>
      <span className="label">{label}</span>
      <div className="chips">
        {options.map((o) => (
          <button key={o.value} type="button" aria-pressed={value === o.value}
            onClick={() => onChange(value === o.value ? "" : o.value)}>
            <span className="chip-title">{o.label}</span>
            {hints[o.label] ? <span className="chip-hint">{hints[o.label]}</span> : null}
          </button>
        ))}
      </div>
      {error ? <span id={errorId} className="error">{error}</span> : null}
    </div>
  );
}

export function FormError({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <Notice tone="neg" title="Não foi salvo">
      <p>{error}</p>
      <p className="small" style={{ marginTop: 4 }}>Seus dados continuam preenchidos. Corrija e toque em salvar de novo.</p>
    </Notice>
  );
}

export function SubmitButton({ busy, online, children }: { busy: boolean; online: boolean; children: ReactNode }) {
  return (
    <div className="stack" style={{ gap: 8 }}>
      <button type="submit" className="btn block" disabled={busy || !online} aria-disabled={busy || !online}>
        {busy ? "Salvando…" : children}
      </button>
      {!online ? <p className="small neg">Sem conexão com o servidor: não é possível salvar agora.</p> : null}
    </div>
  );
}

// --- confirmação ---------------------------------------------------------------------

export function ConfirmButton({ label, title, message, confirmLabel, onConfirm, tone = "danger", disabled = false }: {
  label: string; title: string; message: ReactNode; confirmLabel: string; onConfirm: () => Promise<void> | void; tone?: "danger" | "secondary" | "primary"; disabled?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [busy, setBusy] = useState(false);
  const cls = tone === "primary" ? "btn" : `btn ${tone}`;
  return (
    <>
      <button type="button" className={cls} disabled={disabled} onClick={() => ref.current?.showModal()}>
        {label}
      </button>
      <dialog ref={ref} className="confirm" aria-labelledby={titleId}>
        <div className="stack">
          <h2 id={titleId}>{title}</h2>
          <div>{message}</div>
          <div className="grid-2">
            <button type="button" className="btn secondary" onClick={() => ref.current?.close()}>Voltar</button>
            <button type="button" className={tone === "danger" ? "btn danger" : "btn"} disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await onConfirm();
                } finally {
                  setBusy(false);
                  ref.current?.close();
                }
              }}>
              {busy ? "Aguarde…" : confirmLabel}
            </button>
          </div>
        </div>
      </dialog>
    </>
  );
}

// --- gráficos (sempre com texto) ------------------------------------------------------------

export function Bars({ items, caption }: { items: { label: string; cents: number; tone?: "light" }[]; caption: string }) {
  const max = Math.max(1, ...items.map((i) => Math.abs(i.cents)));
  return (
    <figure className="stack" style={{ margin: 0 }}>
      <figcaption className="sr-only">{caption}</figcaption>
      <div className="bar-chart">
        {items.map((i) => (
          <div className="bar-row" key={i.label}>
            <span className="small" style={{ overflowWrap: "anywhere" }}>{i.label}</span>
            <div className="bar-track" aria-hidden="true">
              <div className={`bar-fill ${i.tone ?? ""}`} style={{ width: `${Math.round((Math.abs(i.cents) / max) * 100)}%` }} />
            </div>
            <Money cents={i.cents} className="small" />
          </div>
        ))}
      </div>
    </figure>
  );
}

export function Progress({ percent, label, caption }: { percent: number; label: string; caption?: string | null }) {
  const p = Math.max(0, Math.min(100, percent));
  return (
    <div>
      <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={p} aria-label={label}>
        <div style={{ width: `${p}%` }} />
      </div>
      {caption === null ? null : <p className="small muted" style={{ marginTop: 4 }}>{caption ?? `${p}% concluído`}</p>}
    </div>
  );
}

export function BackLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className="btn ghost" style={{ alignSelf: "flex-start", paddingLeft: 0 }}>
      ← {children}
    </Link>
  );
}

/** Rola até o topo quando aparece uma mensagem de erro, para não passar despercebida. */
export function useScrollToError(error: string | null) {
  useEffect(() => {
    if (error) window.scrollTo({ top: 0, behavior: "smooth" });
  }, [error]);
}
