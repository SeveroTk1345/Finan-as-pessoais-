// Datas civis como texto "AAAA-MM-DD". "Hoje" vem do servidor (fuso de São Paulo)
// sempre que possível; aqui só há aritmética de calendário, sem fuso.

import { isValidIsoDate } from "./format";

const pad = (n: number) => String(n).padStart(2, "0");

export function isoFromParts(year: number, month: number, day: number): string {
  return `${year}-${pad(month)}-${pad(day)}`;
}

/** Data de hoje no fuso de São Paulo, calculada pelo navegador. */
export function todayInSaoPaulo(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Sao_Paulo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
  return parts; // en-CA formata como AAAA-MM-DD
}

export function monthOf(iso: string): string {
  return iso.slice(0, 7);
}

export function shiftMonth(month: string, delta: number): string {
  const [y, m] = month.split("-").map(Number) as [number, number];
  const index = y * 12 + (m - 1) + delta;
  return `${Math.floor(index / 12)}-${pad((index % 12) + 1)}`;
}

export function monthBounds(month: string): { start: string; end: string } {
  const [y, m] = month.split("-").map(Number) as [number, number];
  const last = [31, (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0 ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1] ?? 31;
  return { start: isoFromParts(y, m, 1), end: isoFromParts(y, m, last) };
}

const MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];

/** "2026-10" -> "outubro de 2026" */
export function monthLabel(month: string): string {
  const [y, m] = month.split("-").map(Number) as [number, number];
  const name = MONTHS[m - 1] ?? "";
  // Só a primeira letra: "Outubro de 2026" (CSS capitalize deixaria "Outubro De 2026").
  return `${name.charAt(0).toUpperCase()}${name.slice(1)} de ${y}`;
}

/** "10/2026" (formato da API nos relatórios) -> "out/2026" */
export function shortMonthLabel(mmYYYY: string): string {
  const [m, y] = mmYYYY.split("/");
  return `${MONTHS[Number(m) - 1]?.slice(0, 3)}/${y}`;
}

// Conversão entre data civil e número de dias (algoritmo de Howard Hinnant),
// sem objeto Date e portanto sem fuso.
function daysFromCivil(y: number, m: number, d: number): number {
  const yy = m <= 2 ? y - 1 : y;
  const era = Math.floor(yy / 400);
  const yoe = yy - era * 400;
  const doy = Math.floor((153 * (m + (m > 2 ? -3 : 9)) + 2) / 5) + d - 1;
  const doe = yoe * 365 + Math.floor(yoe / 4) - Math.floor(yoe / 100) + doy;
  return era * 146097 + doe - 719468;
}

function civilFromDays(z: number): [number, number, number] {
  const zz = z + 719468;
  const era = Math.floor(zz / 146097);
  const doe = zz - era * 146097;
  const yoe = Math.floor((doe - Math.floor(doe / 1460) + Math.floor(doe / 36524) - Math.floor(doe / 146096)) / 365);
  const doy = doe - (365 * yoe + Math.floor(yoe / 4) - Math.floor(yoe / 100));
  const mp = Math.floor((5 * doy + 2) / 153);
  const d = doy - Math.floor((153 * mp + 2) / 5) + 1;
  const m = mp + (mp < 10 ? 3 : -9);
  return [yoe + era * 400 + (m <= 2 ? 1 : 0), m, d];
}

export function addDaysIso(iso: string, days: number): string {
  if (!isValidIsoDate(iso)) throw new Error("data inválida");
  const [y, m, d] = iso.split("-").map(Number) as [number, number, number];
  const [ny, nm, nd] = civilFromDays(daysFromCivil(y, m, d) + days);
  return isoFromParts(ny, nm, nd);
}

export function daysBetween(a: string, b: string): number {
  const [y1, m1, d1] = a.split("-").map(Number) as [number, number, number];
  const [y2, m2, d2] = b.split("-").map(Number) as [number, number, number];
  return daysFromCivil(y2, m2, d2) - daysFromCivil(y1, m1, d1);
}
