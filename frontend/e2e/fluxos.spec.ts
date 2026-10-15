/**
 * Cenários obrigatórios da missão (seção 11), em sequência, como uma pessoa usaria.
 * Cada teste depende dos anteriores (mesmo banco, usuária "ana").
 */
import { expect, type Page, test } from "@playwright/test";

import { flash, login, money, open } from "./helpers";

test.describe.configure({ mode: "serial" });

let page: Page;
const ids: Record<string, string> = {};

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage();
  await login(page, "ana");
});

test.afterAll(async () => {
  await page.close();
});

async function accountBalance(name: string): Promise<string> {
  await open(page, "/contas/");
  const row = page.getByRole("link", { name: new RegExp(name) });
  return (await row.locator(".amount").innerText()).replace(/\s/g, " ");
}

test("1. cria conta bancária e registra uma receita", async () => {
  await open(page, "/contas/nova/");
  await page.getByLabel("Nome da conta").fill("Conta Corrente");
  await money(page, "Quanto há nesta conta", 100000);
  await page.getByRole("button", { name: "Salvar conta" }).click();
  await flash(page, "Conta cadastrada.");

  await open(page, "/lancamentos/novo/?tipo=receita");
  await money(page, "Valor", 350000);
  await page.getByLabel("Descrição").fill("Salário");
  await page.getByLabel("Categoria").selectOption({ label: "Salário" });
  await page.getByRole("button", { name: "Salvar" }).click();
  await flash(page, "Receita salva.");
  expect(await accountBalance("Conta Corrente")).toBe("R$ 4.500,00");
});

test("2. registra uma despesa e o saldo é atualizado", async () => {
  await open(page, "/lancamentos/novo/?tipo=despesa");
  await money(page, "Valor", 12345);
  await page.getByLabel("Descrição").fill("Mercado");
  await page.getByLabel("Categoria").selectOption({ label: "Alimentação" });
  await page.getByRole("button", { name: "Salvar" }).click();
  await flash(page, "Despesa salva.");
  expect(await accountBalance("Conta Corrente")).toBe("R$ 4.376,55");
});

test("3. transfere entre contas próprias sem criar receita", async () => {
  await open(page, "/contas/nova/");
  await page.getByLabel("Nome da conta").fill("Poupança");
  await page.getByLabel("Tipo").selectOption({ label: "Poupança" });
  await page.getByRole("button", { name: "Salvar conta" }).click();
  await flash(page, "Conta cadastrada.");

  await open(page, "/lancamentos/novo/?tipo=transferencia");
  await money(page, "Valor", 50000);
  await page.getByLabel("Sai da conta").selectOption({ label: "Conta Corrente" });
  await page.getByLabel("Entra na conta").selectOption({ label: "Poupança" });
  await page.getByRole("button", { name: "Salvar" }).click();
  await flash(page, "Transferência salva.");

  expect(await accountBalance("Conta Corrente")).toBe("R$ 3.876,55");
  expect(await accountBalance("Poupança")).toBe("R$ 500,00");
  await open(page, "/");
  // O total disponível não muda e a receita do mês continua só o salário.
  await expect(page.locator(".stat-value").first()).toHaveText("R$ 4.376,55");
  await expect(page.getByRole("link", { name: /Recebi neste mês/ })).toContainText("R$ 3.500,00");
});

test("4. cria uma compra parcelada no cartão", async () => {
  await open(page, "/cartoes/novo/");
  await page.getByLabel("Nome do cartão").fill("Cartão Azul");
  await money(page, "Limite total", 500000);
  await page.getByLabel("Dia em que a fatura fecha").fill("25");
  await page.getByLabel("Dia do vencimento").fill("5");
  await page.getByRole("button", { name: "Salvar cartão" }).click();
  await flash(page, "Cartão cadastrado.");

  await page.getByRole("link", { name: /Cartão Azul/ }).click();
  await page.waitForURL(/cartoes\/detalhe/);
  await expect(page.getByRole("heading", { name: "Cartão Azul" })).toBeVisible();
  ids.card = new URL(page.url()).searchParams.get("id") ?? "";
  await page.getByLabel("Descrição").fill("Geladeira");
  await money(page, "Valor total", 120000);
  await page.getByLabel("Em quantas parcelas?").fill("3");
  await page.getByRole("button", { name: "Salvar compra" }).click();
  await flash(page, "Compra salva em 3 parcelas.");
  await expect(page.getByText("Limite usado").locator("..")).toContainText("R$ 1.200,00");
  await expect(page.getByText("Limite disponível").first().locator("..")).toContainText("R$ 3.800,00");
});

test("5. paga a fatura sem duplicar a despesa", async () => {
  await open(page, `/cartoes/detalhe/?id=${ids.card}`);
  await page.locator(".list-row").filter({ hasText: "Aberta" }).click();
  await expect(page.getByText("Falta pagar").locator("..")).toContainText("R$ 400,00");
  await page.getByLabel("Conta usada").selectOption({ label: "Conta Corrente" });
  await page.getByRole("button", { name: "Registrar pagamento" }).click();
  await flash(page, "Fatura paga.");
  expect(await accountBalance("Conta Corrente")).toBe("R$ 3.476,55");
  await open(page, "/");
  // Gasto do mês: mercado + geladeira inteira (dia da compra). O pagamento não soma.
  await expect(page.getByRole("link", { name: /Gastei neste mês/ })).toContainText("R$ 1.323,45");
});

test("6. registra pagamento parcial de dívida", async () => {
  await open(page, "/dividas/nova/");
  await page.getByLabel("Para quem você deve?").fill("Banco Fictício");
  await money(page, "Valor original (quanto pegou ou comprou)", 1000000);
  await money(page, "Valor de cada parcela (opcional)", 100000);
  await page.getByLabel("Total de parcelas (opcional)").fill("10");
  await page.getByRole("button", { name: "Salvar dívida" }).click();
  await flash(page, "Dívida cadastrada.");

  await page.getByRole("link", { name: /Banco Fictício/ }).click();
  await page.getByRole("button", { name: "Valor extra" }).click();
  await money(page, "Valor pago", 50000);
  await page.getByLabel("Conta usada").selectOption({ label: "Conta Corrente" });
  await page.getByRole("button", { name: "Registrar pagamento" }).click();
  await flash(page, "Pagamento registrado.");
  await expect(page.locator(".stat-value").first()).toHaveText("R$ 9.500,00");
  await expect(page.getByText("Você já pagou 0 de 10 parcelas.")).toBeVisible();
});

test("7. cadastra investimento com aporte", async () => {
  await open(page, "/investimentos/novo/");
  await page.getByLabel("Nome", { exact: true }).fill("CDB Banco X");
  await money(page, "Valor aplicado", 200000);
  await page.getByLabel("O dinheiro saiu de uma das minhas contas").check();
  await page.getByLabel("Conta", { exact: true }).selectOption({ label: "Conta Corrente" });
  await page.getByRole("button", { name: "Salvar investimento" }).click();
  await flash(page, "Investimento cadastrado.");
  await page.getByRole("link", { name: /CDB Banco X/ }).click();
  await page.waitForURL(/investimentos\/detalhe/);
  await expect(page.getByText("Quanto você aplicou").locator("..")).toContainText("R$ 2.000,00");
  ids.investment = new URL(page.url()).searchParams.get("id") ?? "";
  // O aporte não é gasto.
  await open(page, "/");
  await expect(page.getByRole("link", { name: /Gastei neste mês/ })).toContainText("R$ 1.323,45");
});

test("8. atualiza manualmente o saldo do investimento", async () => {
  await open(page, `/investimentos/detalhe/?id=${ids.investment}`);
  await money(page, "Saldo atual", 205000);
  await page.getByRole("button", { name: "Salvar valor" }).click();
  await flash(page, "Valor atualizado.");
  await expect(page.locator(".stat-value").first()).toHaveText("R$ 2.050,00");
  await expect(page.getByText("Ganho estimado").locator("..")).toContainText("+R$ 50,00");
});

test("9. consulta relatórios e metas", async () => {
  await open(page, "/planejamento/nova/");
  await money(page, "Quanto quer juntar", 1000000);
  await money(page, "Quanto já tem guardado para isso (opcional)", 100000);
  await money(page, "Quanto pretende guardar por mês (opcional)", 50000);
  await page.getByRole("button", { name: "Criar meta" }).click();
  await flash(page, "Meta criada.");
  await expect(page.getByText("10% concluído")).toBeVisible();

  await open(page, "/relatorios/");
  await expect(page.getByText("Onde gastei")).toBeVisible();
  await expect(page.getByRole("figure", { name: "Gastos por categoria" })).toContainText("Alimentação");
  const gastei = page.locator(".card").first();
  await expect(gastei).toContainText("R$ 1.323,45");
});

test("10. não acessa dados de outra pessoa", async ({ browser }) => {
  await open(page, "/contas/");
  await page.getByRole("link", { name: /Conta Corrente/ }).click();
  await page.waitForURL(/contas\/detalhe/);
  const anaAccount = new URL(page.url()).searchParams.get("id") ?? "";

  const bruno = await browser.newPage();
  await login(bruno, "bruno");
  // Pela API, com o ID conhecido.
  const res = await bruno.request.get(`/api/contas/${anaAccount}`);
  expect(res.status()).toBe(404);
  expect(await res.text()).not.toContain("Conta Corrente");
  // Pela tela.
  await open(bruno, `/contas/detalhe/?id=${anaAccount}`);
  await expect(bruno.getByText("Conta não encontrada.")).toBeVisible();
  await open(bruno, "/contas/");
  await expect(bruno.getByText("Nenhuma conta cadastrada")).toBeVisible();
  await open(bruno, "/");
  await expect(bruno.locator(".stat-value").first()).toHaveText("R$ 0,00");
  await bruno.close();
});

test("11. recarrega a página e os dados continuam salvos", async () => {
  await open(page, "/lancamentos/");
  await page.reload();
  await expect(page.getByRole("link", { name: /Mercado/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /Salário/ })).toBeVisible();
});

test("13. sem internet, avisa e não deixa salvar; resposta perdida não duplica", async () => {
  await open(page, "/lancamentos/novo/?tipo=despesa");
  await money(page, "Valor", 999);
  await page.getByLabel("Descrição").fill("Padaria sem internet");

  // Sem conexão: aviso no alto e botão bloqueado, sem perder o que foi digitado.
  await page.context().setOffline(true);
  await expect(page.getByRole("alert").filter({ hasText: "Sem conexão com o servidor" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Salvar" })).toBeDisabled();
  await expect(page.getByText("não é possível salvar agora")).toBeVisible();
  await page.context().setOffline(false);
  await expect(page.getByRole("button", { name: "Salvar" })).toBeEnabled({ timeout: 15_000 });
  await expect(page.getByLabel("Descrição")).toHaveValue("Padaria sem internet");

  // A conexão cai no meio do envio: o servidor grava, mas a resposta não chega.
  await page.route("**/api/lancamentos", async (route) => {
    await route.fetch();
    await route.abort("connectionreset");
  });
  await page.getByRole("button", { name: "Salvar" }).click();
  await expect(page.getByText("Não foi salvo")).toBeVisible();
  await page.unroute("**/api/lancamentos");
  // A pessoa toca em salvar de novo: a mesma operação é reconhecida e não duplica.
  await expect(page.getByRole("button", { name: "Salvar" })).toBeEnabled({ timeout: 15_000 });
  await page.getByRole("button", { name: "Salvar" }).click();
  await flash(page, "Despesa salva.");
  await open(page, "/lancamentos/");
  await expect(page.getByRole("link", { name: /Padaria sem internet/ })).toHaveCount(1);
});

test("sair e voltar pelo navegador não mostra dados", async () => {
  await open(page, "/contas/");
  await expect(page.getByText("Conta Corrente").first()).toBeVisible();
  await page.getByRole("button", { name: "Sair" }).click();
  await page.waitForURL(/\/entrar\/$/);
  await page.goBack();
  await page.waitForURL(/\/entrar\/$/, { timeout: 15_000 });
  await expect(page.getByText("Conta Corrente")).toHaveCount(0);
  const res = await page.request.get("/api/contas");
  expect(res.status()).toBe(401);
});
