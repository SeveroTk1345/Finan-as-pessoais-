// Formatos das respostas da API usados nas telas. Valores em centavos (inteiros)
// e datas como texto "AAAA-MM-DD".

export type Account = {
  id: string;
  name: string;
  institution: string | null;
  kind: "corrente" | "poupanca" | "especie" | "outra";
  initial_balance_cents: number;
  initial_balance_date: string;
  balance_cents: number;
  daily_use: boolean;
  is_active: boolean;
  note: string | null;
  version: number;
  tx_count?: number;
};

export type Category = { id: string; name: string; kind: "receita" | "despesa"; is_archived: boolean; is_system: boolean };

export type Transaction = {
  id: string;
  account_id: string;
  account_name: string;
  direction: "entrada" | "saida";
  amount_cents: number;
  tx_date: string;
  kind: string;
  description: string;
  category_id: string | null;
  category_name: string | null;
  expense_nature: string | null;
  note: string | null;
  status: "ativo" | "cancelado";
  version: number;
  transfer_id: string | null;
  transfer_other_account_name: string | null;
  bill_id: string | null;
  card_id: string | null;
  debt_id: string | null;
  history?: { action: string; before_data: Record<string, unknown> | null; after_data: Record<string, unknown> | null; created_at: string }[];
};

export type Bill = {
  id: string | null;
  kind: "pagar" | "receber";
  description: string;
  amount_cents: number;
  due_date: string;
  category_id: string | null;
  category_name: string | null;
  account_id: string | null;
  rule_id: string | null;
  occurrence_date: string | null;
  situation: string;
  paid_cents: number;
  remaining_cents: number;
  due_soon: boolean;
  virtual: boolean;
  version: number | null;
  note: string | null;
  payments?: { id: string; amount_cents: number; tx_date: string; status: string; account_name: string }[];
};

export type Obligation = {
  source: "conta" | "fatura" | "divida";
  id: string | null;
  rule_id?: string | null;
  description: string;
  due_date: string;
  amount_cents: number;
  overdue: boolean;
  virtual?: boolean;
  invoice_status?: string;
};

export type Invoice = {
  due_date: string;
  closing_date: string;
  charges_cents: number;
  credits_cents: number;
  carried_credit_cents: number;
  payments_cents: number;
  total_cents: number;
  remaining_cents: number;
  credit_left_cents: number;
  status: string;
};

export type Card = {
  id: string;
  name: string;
  institution: string | null;
  limit_cents: number;
  closing_day: number;
  due_day: number;
  closing_day_goes_next: boolean;
  is_active: boolean;
  version: number;
  limit_used_cents: number;
  limit_available_cents: number;
  credit_balance_cents: number;
  open_invoice: Invoice;
  invoices_to_pay: Invoice[];
  outstanding_cents: number;
  invoices?: Invoice[];
};

export type Debt = {
  id: string;
  creditor: string;
  description: string | null;
  kind: string;
  original_amount_cents: number;
  balance_cents: number;
  balance_estimated: boolean;
  interest_rate: string | null;
  rate_period: "mensal" | "anual" | null;
  installments_total: number | null;
  installments_paid: number;
  installments_remaining: number | null;
  installment_amount_cents: number | null;
  next_due_date: string | null;
  overdue: boolean;
  status: string;
  is_card_channel: boolean;
  total_paid_cents: number;
  interest_paid_cents: number | null;
  renegotiated_from_id: string | null;
  version: number;
  note: string | null;
  payments?: { id: string; tx_date: string; amount_cents: number; debt_interest_cents: number | null; debt_payment_type: string; status: string; account_name: string }[];
  events?: { id: string; event_date: string; kind: string; amount_cents: number; description: string; status: string }[];
};

export type Investment = {
  id: string;
  asset_class: "renda_fixa" | "renda_variavel" | "outros";
  product_type: string;
  name: string;
  institution: string | null;
  ticker: string | null;
  indexer: string | null;
  rate_description: string | null;
  maturity_date: string | null;
  liquidity: string | null;
  is_active: boolean;
  invested_cents: number;
  total_contributed_cents: number;
  total_withdrawn_cents: number;
  income_received_cents: number;
  current_value_cents: number | null;
  value_date: string | null;
  value_is_stale: boolean;
  estimated_gain_cents: number | null;
  annual_return: string | null;
  quantity?: string;
  average_price_cents?: number | null;
  realized_gain_cents?: number;
  version: number;
  movements?: { id: string; movement_date: string; kind: string; label: string; amount_cents: number; fees_cents: number; quantity: string | null; status: string; account_name: string | null }[];
  valuations?: { id: string; valuation_date: string; value_cents: number | null; unit_price_cents: number | null }[];
  allowed_kinds?: string[];
};

export type Goal = {
  id: string;
  name: string;
  kind: string;
  kind_label: string;
  target_cents: number;
  target_date: string | null;
  planned_monthly_cents: number | null;
  assumed_annual_rate: string | null;
  accumulated_cents: number;
  missing_cents: number;
  percent: number;
  months_needed: number | null;
  projected_date: string | null;
  on_track: boolean | null;
  assumption: string;
  is_active: boolean;
  version: number;
  contributions?: { id: string; contribution_date: string; direction: string; amount_cents: number; note: string | null }[];
};
