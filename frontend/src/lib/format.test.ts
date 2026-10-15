import { describe, expect, it } from "vitest";

import {
  FormatError,
  MAX_ABS_CENTS,
  digitsToCents,
  formatCents,
  formatIsoDate,
  isValidIsoDate,
} from "./format";

// Este arquivo roda em três fusos (ver script "test" do package.json).
describe(`fuso do processo: ${process.env.TZ ?? "padrão"}`, () => {
  describe("formatCents", () => {
    it.each([
      [0, "R$ 0,00"],
      [5, "R$ 0,05"],
      [100, "R$ 1,00"],
      [123456, "R$ 1.234,56"],
      [100000000, "R$ 1.000.000,00"],
      [-123456, "-R$ 1.234,56"],
      [-5, "-R$ 0,05"],
      [MAX_ABS_CENTS, "R$ 1.000.000.000.000,00"],
    ])("%i -> %s", (cents, text) => {
      expect(formatCents(cents)).toBe(text);
    });

    it.each([0.1, 1.5, NaN, Infinity, MAX_ABS_CENTS + 1, 2 ** 53])("rejeita %s", (bad) => {
      expect(() => formatCents(bad)).toThrow(FormatError);
    });

    it("bate com o formato do backend (app/domain/money.py format_brl)", () => {
      // Mesmos casos de tests/domain/test_money.py::test_format_brl.
      expect(formatCents(123456)).toBe("R$ 1.234,56");
      expect(formatCents(-5)).toBe("-R$ 0,05");
    });
  });

  describe("datas civis", () => {
    it("não muda o dia por causa do fuso", () => {
      // new Date("2026-10-15") viraria 14/10 em São Paulo; aqui não pode.
      expect(formatIsoDate("2026-10-15")).toBe("15/10/2026");
      expect(formatIsoDate("2026-01-01")).toBe("01/01/2026");
      expect(formatIsoDate("2026-12-31")).toBe("31/12/2026");
    });

    it.each(["2028-02-29", "2000-02-29", "2026-02-28"])("aceita %s", (d) => {
      expect(isValidIsoDate(d)).toBe(true);
    });

    it.each(["2026-02-29", "2100-02-29", "2026-13-01", "2026-00-10", "2026-04-31", "15/10/2026", "2026-1-5", ""])(
      "rejeita %s",
      (d) => {
        expect(isValidIsoDate(d)).toBe(false);
        expect(() => formatIsoDate(d)).toThrow(FormatError);
      },
    );
  });

  describe("digitsToCents (máscara de valor)", () => {
    it.each([
      ["", 0],
      ["0", 0],
      ["1", 1],
      ["12", 12],
      ["123456", 123456],
      ["R$ 1.234,56", 123456],
      ["000123", 123],
    ])("%s -> %i", (input, cents) => {
      expect(digitsToCents(input)).toBe(cents);
    });

    it("apagar o último dígito volta uma casa", () => {
      expect(formatCents(digitsToCents("123456"))).toBe("R$ 1.234,56");
      expect(formatCents(digitsToCents("12345"))).toBe("R$ 123,45");
    });

    it("rejeita valores acima do limite", () => {
      expect(() => digitsToCents("9999999999999999")).toThrow(FormatError);
      expect(() => digitsToCents("100000000000001")).toThrow(FormatError);
    });
  });
});
