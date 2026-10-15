"use client";

import { useApi } from "./hooks";
import type { Account, Category } from "./types";

export const ACCOUNT_KINDS: Record<string, string> = {
  corrente: "Conta corrente",
  poupanca: "Poupança",
  especie: "Dinheiro em espécie",
  outra: "Outra",
};

export const TX_KINDS: Record<string, string> = {
  receita: "Receita",
  despesa: "Despesa",
  transferencia: "Transferência",
  ajuste: "Ajuste de saldo",
  pagamento_fatura: "Pagamento de fatura",
  pagamento_divida: "Pagamento de dívida",
  entrada_emprestimo: "Entrada de empréstimo",
  reembolso: "Reembolso",
  investimento: "Investimento",
};

export const DEBT_KINDS: Record<string, string> = {
  emprestimo: "Empréstimo",
  financiamento: "Financiamento",
  parcelamento: "Compra parcelada (fora do cartão)",
  renegociacao: "Renegociação",
  parcelamento_fatura: "Parcelamento de fatura",
  outra: "Outra dívida",
};

export const NATURES = [
  { value: "fixa", label: "Fixa (todo mês)" },
  { value: "variavel", label: "Variável" },
  { value: "extraordinaria", label: "Extraordinária (fora do comum)" },
];

export function useAccounts(activeOnly = true) {
  const r = useApi<Account[]>(`/contas?incluir_inativas=${activeOnly ? "false" : "true"}`);
  const options = r.state === "ready" ? r.data.map((a) => ({ value: a.id, label: a.name })) : [];
  return { ...r, options };
}

export function useCategories(kind: "receita" | "despesa") {
  const r = useApi<Category[]>("/categorias");
  const options =
    r.state === "ready"
      ? r.data.filter((c) => c.kind === kind && !c.is_archived).map((c) => ({ value: c.id, label: c.name }))
      : [];
  return { ...r, options };
}
