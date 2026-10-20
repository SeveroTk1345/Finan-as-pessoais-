/**
 * Entrar com digital ou rosto. O Chromium simula o sensor do aparelho com um
 * autenticador virtual (protocolo DevTools), que "confirma a digital" sozinho.
 */
import { expect, test } from "@playwright/test";

import { login, ready } from "./helpers";

test("ativa a digital pelo convite do Início e depois entra sem digitar a senha", async ({ page }) => {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("WebAuthn.enable");
  await cdp.send("WebAuthn.addVirtualAuthenticator", {
    options: {
      protocol: "ctap2",
      transport: "internal",
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
    },
  });

  await login(page, "carla");
  const offer = page.getByRole("heading", { name: "Entrar sem digitar a senha" });
  await expect(offer).toBeVisible();
  await page.getByRole("link", { name: "Ativar", exact: true }).click();
  await page.waitForURL(/perfil/);
  await ready(page);
  await page.getByRole("button", { name: "Ativar neste aparelho" }).click();
  await expect(page.getByRole("list", { name: "Aparelhos ativados" })).toContainText("Ativado em");

  await page.getByRole("button", { name: "Sair", exact: true }).click();
  await page.waitForURL(/entrar/);
  await ready(page);
  await expect(page.getByLabel("Usuário")).toHaveValue("");
  await page.getByRole("button", { name: "Entrar com digital ou rosto" }).click();
  await expect(page.getByText("Conectado como")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Olá, Carla" })).toBeVisible();
  // Já ativado: o convite não aparece mais.
  await expect(offer).toHaveCount(0);
});

test("sem sensor no aparelho, o login mostra só usuário e senha", async ({ page }) => {
  await page.goto("/entrar/");
  await ready(page);
  await expect(page.getByLabel("Usuário")).toBeVisible();
  await expect(page.getByRole("button", { name: "Entrar com digital ou rosto" })).toHaveCount(0);
});
