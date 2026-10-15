/**
 * Registrar gasto do jeito simples: botões de categoria, "Repete" e compra parcelada
 * no carnê. Usuária "carla", com conta própria criada aqui.
 */
import { expect, type Page, test } from "@playwright/test";

import { flash, login, money, open } from "./helpers";

test.describe.configure({ mode: "serial" });

let page: Page;

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage();
  await login(page, "carla");
  await open(page, "/contas/nova/");
  await page.getByLabel("Nome da conta").fill("Conta da Carla");
  await money(page, "Quanto há nesta conta", 500000);
  await page.getByRole("button", { name: "Salvar conta" }).click();
  await flash(page, "Conta cadastrada.");
});

test.afterAll(async () => {
  await page.close();
});

test("sem escolher com o que foi o gasto, não salva e explica", async () => {
  await open(page, "/lancamentos/novo/?tipo=despesa");
  await money(page, "Valor", 5000);
  await page.getByRole("button", { name: "Salvar" }).click();
  await expect(page.getByText("Escolha com o que foi o gasto.")).toBeVisible();
});

test("gasto que se repete todo mês aparece nos próximos meses em Contas a pagar", async () => {
  await open(page, "/lancamentos/novo/?tipo=despesa");
  await money(page, "Valor", 11990);
  await page.getByRole("button", { name: /^Faculdade e cursos/ }).click();
  await page.getByRole("button", { name: "Repete", exact: true }).click();
  await expect(page.getByLabel("Com que frequência")).toHaveValue("mensal");
  await page.getByRole("button", { name: "Salvar" }).click();
  await flash(page, "As próximas vezes aparecem em Contas a pagar.");
  await expect(page.getByRole("link", { name: /Faculdade e cursos/ })).toBeVisible();

  await open(page, "/a-pagar/");
  await page.getByRole("button", { name: /Próximo/ }).click();
  await expect(page.getByRole("list", { name: "Contas do mês" })).toContainText("Faculdade e cursos");
  await expect(page.getByRole("list", { name: "Contas do mês" })).toContainText("repete");
});

test("R$ 1.000,00 no carnê em 10x vira 10 parcelas de R$ 100,00", async () => {
  await open(page, "/lancamentos/novo/?tipo=despesa");
  await money(page, "Valor", 100000);
  await page.getByRole("button", { name: /^Roupas e acessórios/ }).click();
  await page.getByRole("button", { name: "Carnê ou boleto" }).click();
  await page.getByLabel("Em quantas parcelas?").fill("10");
  await expect(page.getByText("10x de R$ 100,00")).toBeVisible();
  await page.getByLabel("Descrição (opcional)").fill("Casaco");
  await page.getByRole("button", { name: "Salvar" }).click();
  await flash(page, "as 10 parcelas estão em Contas a pagar");

  await page.getByRole("button", { name: /Próximo/ }).click();
  const list = page.getByRole("list", { name: "Contas do mês" });
  await expect(list).toContainText("Casaco · parcela 1 de 10");
  await expect(list).toContainText("R$ 100,00");

  // Quanto devo inclui o carnê; o gasto só conta quando a parcela é paga.
  await open(page, "/");
  await expect(page.getByText("Quanto devo").locator("..")).toContainText("R$ 1.000,00");

  await open(page, "/a-pagar/");
  await page.getByRole("button", { name: /Próximo/ }).click();
  await page.getByRole("link", { name: /Casaco · parcela 1 de 10/ }).click();
  await page.waitForURL(/a-pagar\/detalhe/);
  await page.getByRole("button", { name: "Cancelar as parcelas que faltam" }).click();
  await page.getByRole("button", { name: "Sim, cancelar as que faltam" }).click();
  await flash(page, "10 parcelas canceladas.");
});
