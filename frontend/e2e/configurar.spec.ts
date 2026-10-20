/**
 * Configuração pelo navegador (/configurar): usada onde não há terminal (Render).
 * O ambiente de teste já tem as 3 contas; aqui a senha da Carla é redefinida para a
 * mesma, para não atrapalhar os outros testes.
 */
import { expect, test } from "@playwright/test";

import { login, open } from "./helpers";

const CODE = "codigo-sintetico-de-configuracao-e2e";

test("mostra 3 de 3 contas, recusa código errado e redefine senha", async ({ page }) => {
  await open(page, "/configurar/");
  await expect(page.getByText("3 de 3")).toBeVisible();
  await expect(page.getByText("As 3 contas já foram criadas.")).toBeVisible();

  const reset = page.locator("form", { hasText: "Alguém esqueceu a senha?" });
  await page.getByLabel("Código de configuração").fill("chute");
  await reset.getByLabel("Usuário", { exact: true }).fill("carla");
  await reset.getByLabel("Nova senha", { exact: true }).fill("castelo-rosa-2026");
  await reset.getByLabel("Repita a nova senha").fill("castelo-rosa-2026");
  await reset.getByRole("button", { name: "Trocar senha" }).click();
  await expect(reset.getByText("Código de configuração incorreto.")).toBeVisible();

  await page.getByLabel("Código de configuração").fill(CODE);
  await reset.getByRole("button", { name: "Trocar senha" }).click();
  await expect(reset.getByText("Senha de carla trocada.")).toBeVisible();

  await login(page, "carla");
});
