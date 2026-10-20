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

/** Exemplos mostrados nos botões das categorias padrão (as criadas pela pessoa não têm). */
export const CATEGORY_HINTS: Record<string, string> = {
  Mercado: "Supermercado, feira, padaria",
  "Contas da casa": "Luz, água, gás, internet, telefone",
  Casa: "Aluguel, condomínio, móveis, consertos",
  Carro: "Combustível, manutenção, seguro, IPVA",
  Transporte: "Ônibus, aplicativo, táxi",
  "Medicamentos e saúde": "Farmácia, consultas, exames, plano",
  "Faculdade e cursos": "Mensalidade, material, livros",
  "Roupas e acessórios": "Roupas, calçados, bolsas",
  "Restaurante e lanche": "Comer fora, delivery",
  "Cuidados pessoais": "Cabelo, beleza, higiene",
  Lazer: "Passeios, viagens, cinema",
  Assinaturas: "Streaming, aplicativos, clubes",
  Presentes: "Aniversários, datas especiais",
  "Juros e tarifas": "Tarifas do banco, juros, IOF",
  Outros: "O que não se encaixa acima",
  Salário: "Pagamento do trabalho",
  Aposentadoria: "INSS, previdência",
  "Renda extra": "Vendas, bicos, serviços",
  Benefícios: "Auxílios, bolsas",
};

