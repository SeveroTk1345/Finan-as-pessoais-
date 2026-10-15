// Formatação para exibição. Nenhuma regra financeira aqui: os cálculos são do backend.
// Dinheiro chega da API como inteiro em centavos; datas civis como texto "AAAA-MM-DD".

/** Mesmo limite do backend (app/domain/money.py): 1 trilhão de reais. */
export const MAX_ABS_CENTS = 100_000_000_000_000;

export class FormatError extends Error {}

function assertCents(cents: number): void {
  if (!Number.isSafeInteger(cents) || Math.abs(cents) > MAX_ABS_CENTS) {
    throw new FormatError(`centavos inválidos: ${String(cents)}`);
  }
}

/** 123456 -> "R$ 1.234,56"; -5 -> "-R$ 0,05". Só aritmética inteira. */
export function formatCents(cents: number): string {
  assertCents(cents);
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  const reais = Math.trunc(abs / 100); // inteiros seguros: divisão exata após trunc
  const centavos = abs % 100;
  const grouped = String(reais).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${sign}R$ ${grouped},${String(centavos).padStart(2, "0")}`;
}

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

function daysInMonth(year: number, month: number): number {
  const leap = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
  return [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1] ?? 0;
}

/** Valida "AAAA-MM-DD" sem passar por Date (sem fuso, sem UTC). */
export function isValidIsoDate(value: string): boolean {
  const m = ISO_DATE.exec(value);
  if (!m) return false;
  const year = Number(m[1]);
  const month = Number(m[2]);
  const day = Number(m[3]);
  return month >= 1 && month <= 12 && day >= 1 && day <= daysInMonth(year, month);
}

/** "2026-10-15" -> "15/10/2026", independente do fuso do aparelho. */
export function formatIsoDate(value: string): string {
  if (!isValidIsoDate(value)) {
    throw new FormatError(`data inválida: ${value}`);
  }
  const [year, month, day] = value.split("-");
  return `${day}/${month}/${year}`;
}

/**
 * Campo de valor com máscara de centavos, como nos apps de banco:
 * o usuário digita só números e eles entram pela direita.
 * "123456" -> 123456 centavos (R$ 1.234,56). Ignora tudo que não for dígito.
 */
export function digitsToCents(input: string): number {
  const digits = input.replace(/\D/g, "").replace(/^0+(?=\d)/, "");
  if (digits === "") return 0;
  // 15 dígitos = R$ 9.999.999.999.999,99, acima do limite: rejeita antes de virar Number.
  if (digits.length > 15) {
    throw new FormatError("valor muito alto");
  }
  const cents = Number(digits);
  assertCents(cents);
  return cents;
}

/** Taxa anual em fração vinda da API ("0.1234") -> "12,34% ao ano". Só exibição. */
export function formatAnnualRate(rate: string | null): string | null {
  if (rate === null) return null;
  const v = Math.round(Number(rate) * 10000) / 100;
  return `${v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}% ao ano`;
}
