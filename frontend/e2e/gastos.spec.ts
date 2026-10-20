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

test("plano do mês divide a renda e projeta o investimento", async () => {
  await open(page, "/planejamento/");
  await page.getByRole("link", { name: /Plano do mês/ }).click();
  await page.waitForURL(/planejamento\/plano/);
  await money(page, "Quanto você recebe por mês", 300000);
  // Contas do mês: a faculdade (R$ 119,90); o carnê cancelado não conta.
  await expect(page.getByRole("heading", { name: "Como dividir R$ 3.000,00" })).toBeVisible();
  const result = page.getByRole("region", { name: /Como dividir/ });
  await expect(result).toContainText("R$ 119,90");
  await expect(result).toContainText("R$ 600,00"); // 20% da renda
  await expect(result).toContainText("R$ 2.280,10"); // livre para gastar
  await page.getByLabel("Quanto rende ao ano, em % (opcional)").fill("10");
  const projection = page.getByRole("list", { name: "Projeção do investimento" });
  await expect(projection).toContainText("Você colocou R$ 7.200,00"); // 12 x R$ 600,00 em 1 ano
  await expect(page.getByText(/10% ao ano informado por você/)).toBeVisible();
});

test("o total dos próximos 30 dias é a soma do que aparece na lista", async () => {
  // Conta avulsa vencendo hoje: precisa aparecer no quadro e no total.
  await open(page, "/a-pagar/nova/?tipo=pagar");
  await page.getByLabel("Descrição").fill("Dentista");
  await money(page, "Valor", 25000);
  await page.getByRole("button", { name: "Salvar" }).click();
  await flash(page, "Salvo.");
  await open(page, "/a-pagar/");
  const box = page.getByRole("region", { name: "Próximos 30 dias" });
  const cents = (text: string) => Number(text.replace(/[^\d-]/g, ""));
  const total = cents(await box.locator("p strong").first().innerText());
  const items = await box.locator(".list .amount").allInnerTexts();
  expect(items.length).toBeGreaterThan(0);
  expect(items.reduce((s, t) => s + cents(t), 0)).toBe(total);
});
