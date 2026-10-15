import { describe, expect, it } from "vitest";

import { orderInvoices } from "./invoices";
import type { Invoice } from "./types";

const inv = (due_date: string, status: string, remaining_cents: number): Invoice => ({
  due_date, closing_date: due_date, charges_cents: 0, credits_cents: 0, carried_credit_cents: 0,
  payments_cents: 0, total_cents: 0, remaining_cents, credit_left_cents: 0, status,
});

describe("orderInvoices", () => {
  it("põe vencida e aberta antes das futuras, e as pagas por último", () => {
    const out = orderInvoices([
      inv("2027-01-05", "futura", 100),
      inv("2026-09-05", "paga", 0),
      inv("2026-11-05", "aberta", 100),
      inv("2026-12-05", "futura", 100),
      inv("2026-10-05", "vencida", 100),
      inv("2026-08-05", "paga", 0),
    ]).map((i) => i.due_date);
    expect(out).toEqual(["2026-10-05", "2026-11-05", "2026-12-05", "2027-01-05", "2026-09-05", "2026-08-05"]);
  });

  it("não altera a lista recebida", () => {
    const list = [inv("2026-12-05", "futura", 1), inv("2026-10-05", "vencida", 1)];
    orderInvoices(list);
    expect(list.map((i) => i.due_date)).toEqual(["2026-12-05", "2026-10-05"]);
  });
});
