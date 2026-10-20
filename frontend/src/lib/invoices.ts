import type { Invoice } from "./types";

/**
 * Ordem de leitura das faturas: primeiro o que precisa de ação (vencidas, fechadas e
 * aberta com saldo, da mais antiga para a mais nova), depois as futuras em ordem de
 * vencimento e, por último, as já quitadas, da mais recente para a mais antiga.
 */
export function orderInvoices(invoices: readonly Invoice[]): Invoice[] {
  const group = (i: Invoice) => (i.remaining_cents <= 0 ? 2 : i.status === "futura" ? 1 : 0);
  return [...invoices].sort((a, b) => {
    const g = group(a) - group(b);
    if (g !== 0) return g;
    const asc = a.due_date < b.due_date ? -1 : a.due_date > b.due_date ? 1 : 0;
    return group(a) === 2 ? -asc : asc;
  });
}
