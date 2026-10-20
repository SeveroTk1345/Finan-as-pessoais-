/**
 * Prioridade 1: atalhos de gasto, teto por categoria, gasto por dia, calendário de
 * contas, contas anuais e resumo do mês. Usuário "bruno" (o cenário 10 de fluxos.spec
 * já conferiu que ele começa sem dados).
 */
import { expect, type Page, test } from "@playwright/test";

import { flash, login, money, open } from "./helpers";

test.describe.configure({ mode: "serial" });

let page: Page;

async function expense(cents: number, category: RegExp, description: string): Promise<void> {
  await open(page, "/lancamentos/novo/?tipo=despesa");
  await money(page, "Valor", cents);
  await page.getByRole("button", { name: category }).click();
  await page.getByLabel("Descrição (opcional)").fill(description);
  await page.getByRole("button", { name: "Salvar" }).click();
  await flash(page, "Despesa salva.");
}

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage();
  await login(page, "bruno");
  await open(page, "/contas/nova/");
  await page.getByLabel("Nome da conta").fill("Conta do Bruno");
  await money(page, "Quanto há nesta conta", 500000);
  await page.getByRole("button", { name: "Salvar conta" }).click();
  await flash(page, "Conta cadastrada.");
});

test.afterAll(async () => {
  await page.close();
});

test("gasto repetido vira atalho que abre o formulário preenchido", async () => {
  await expense(1500, /^Mercado/, "Padaria");
  await expense(1500, /^Mercado/, "Padaria");
  await open(page, "/");
  const shortcuts = page.getByRole("region", { name: "Gastos de sempre" });
  await shortcuts.getByRole("link", { name: /Padaria/ }).click();
  await page.waitForURL(/lancamentos\/novo/);
  await expect(page.getByLabel("Valor")).toHaveValue("R$ 15,00");
  await expect(page.getByLabel("Descrição (opcional)")).toHaveValue("Padaria");
  await expect(page.getByRole("button", { name: /^Mercado/ })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Salvar" }).click();
  await flash(page, "Despesa salva.");
});

test("Início mostra quanto dá para gastar por dia", async () => {
  await open(page, "/");
  await expect(page.getByText(/Dá para gastar cerca de R\$ [\d.,]+ por dia/)).toBeVisible();
});

test("teto por categoria avisa no Início quando passa", async () => {
  await open(page, "/planejamento/");
  await page.getByRole("link", { name: /Teto de gastos/ }).click();
  await page.waitForURL(/planejamento\/tetos/);
  const card = page.getByRole("listitem").filter({ has: page.getByRole("heading", { name: "Mercado", exact: true }) });
  await card.getByRole("button", { name: "Definir teto" }).click();
  await money(page, "Teto por mês para Mercado", 4000);
  await page.getByRole("button", { name: "Salvar teto" }).click();
  await flash(page, "Teto de Mercado salvo.");
  await expect(card).toContainText("R$ 45,00 de R$ 40,00 (112%)");
  await expect(card).toContainText("Passou do teto");
  await open(page, "/");
  await expect(page.getByText("Mercado: R$ 45,00 de R$ 40,00 (112%)")).toBeVisible();
});

test("calendário mostra a conta no dia do vencimento", async () => {
  await open(page, "/a-pagar/nova/?tipo=pagar");
  await page.getByLabel("Descrição").fill("Luz");
  await money(page, "Valor", 18740);
  await page.getByRole("button", { name: "Salvar" }).click();
  await flash(page, "Salvo.");
  await open(page, "/a-pagar/");
  await page.getByRole("link", { name: "Ver calendário" }).click();
  await page.waitForURL(/calendario/);
  // Hoje já vem escolhido: a conta de hoje aparece na lista do dia.
  await expect(page.getByRole("region", { name: /\(/ }).getByRole("link", { name: /Luz/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /1 item, R\$ 187,40 a pagar/ })).toHaveAttribute("aria-pressed", "true");
});

test("conta anual aparece no plano do mês com quanto guardar por mês", async () => {
  await open(page, "/a-pagar/nova/?tipo=pagar");
  await page.getByLabel("Descrição").fill("IPVA");
  await money(page, "Valor", 120000);
  await page.getByLabel("Repetir").selectOption({ label: "Todo ano" });
  await page.getByRole("button", { name: "Salvar" }).click();
  await flash(page, "Salvo.");
  await open(page, "/planejamento/plano/");
  const annual = page.getByRole("region", { name: "Contas de uma vez por ano" });
  await expect(annual).toContainText("IPVA");
  await expect(annual).toContainText("R$ 1.200,00. Vence"); // vence hoje: "Vence neste mês"
  await expect(annual).toContainText("Separando");
});

test("relatórios trazem o resumo do mês em frases", async () => {
  await open(page, "/relatorios/");
  const summary = page.getByRole("region", { name: /Resumo de/ });
  await expect(summary).toContainText("Até agora");
  await expect(summary).toContainText("Onde mais gastou: Mercado (R$ 45,00)");
  await expect(summary).toContainText("Passou do teto em: Mercado.");
});
