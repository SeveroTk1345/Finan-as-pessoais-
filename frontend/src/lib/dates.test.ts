import { describe, expect, it } from "vitest";

import { addDaysIso, daysBetween, monthBounds, monthLabel, shiftMonth, shortMonthLabel, todayInSaoPaulo } from "./dates";

describe(`datas (fuso do processo: ${process.env.TZ ?? "padrão"})`, () => {
  it("hoje em São Paulo independe do fuso do aparelho", () => {
    // 15/10/2026 02:00 UTC ainda é 14/10 em São Paulo.
    // Instantes UTC explícitos, só para simular o relógio do aparelho.
    // eslint-disable-next-line no-restricted-syntax
    const late = new Date(Date.UTC(2026, 9, 15, 2, 0));
    // eslint-disable-next-line no-restricted-syntax
    const early = new Date(Date.UTC(2026, 9, 15, 3, 0));
    expect(todayInSaoPaulo(late)).toBe("2026-10-14");
    expect(todayInSaoPaulo(early)).toBe("2026-10-15");
  });

  it("navega entre meses e atravessa o ano", () => {
    expect(shiftMonth("2026-12", 1)).toBe("2027-01");
    expect(shiftMonth("2026-01", -1)).toBe("2025-12");
    expect(shiftMonth("2026-10", -22)).toBe("2024-12");
  });

  it("limites do mês, inclusive fevereiro bissexto", () => {
    expect(monthBounds("2028-02")).toEqual({ start: "2028-02-01", end: "2028-02-29" });
    expect(monthBounds("2026-02")).toEqual({ start: "2026-02-01", end: "2026-02-28" });
    expect(monthBounds("2026-12")).toEqual({ start: "2026-12-01", end: "2026-12-31" });
  });

  it("soma dias sem objeto Date", () => {
    expect(addDaysIso("2026-12-31", 1)).toBe("2027-01-01");
    expect(addDaysIso("2028-02-28", 1)).toBe("2028-02-29");
    expect(addDaysIso("2026-03-01", -1)).toBe("2026-02-28");
    expect(addDaysIso("2026-10-15", 30)).toBe("2026-11-14");
    expect(daysBetween("2026-10-15", "2026-11-14")).toBe(30);
  });

  it("nomes dos meses em português", () => {
    expect(monthLabel("2026-03")).toBe("Março de 2026");
    expect(shortMonthLabel("10/2026")).toBe("out/2026");
  });
});
