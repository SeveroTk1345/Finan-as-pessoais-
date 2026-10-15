import { expect, type Page } from "@playwright/test";

// Senhas sintéticas criadas por scripts/stack-local.sh. Nada aqui é dado real.
export const USERS = {
  ana: "abacate-verde-2026",
  bruno: "bicicleta-azul-2026",
  carla: "castelo-rosa-2026",
} as const;

export async function ready(page: Page): Promise<void> {
  await page.locator('html[data-ready="1"]').waitFor({ state: "attached" });
}

export async function login(page: Page, user: keyof typeof USERS): Promise<void> {
  await page.goto("/entrar/");
  await ready(page);
  await page.getByLabel("Usuário").fill(user);
  await page.getByLabel("Senha").fill(USERS[user]);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await page.waitForURL(/\/$/);
  await ready(page);
  await expect(page.getByText("Conectado como")).toBeVisible();
}

export async function open(page: Page, path: string): Promise<void> {
  await page.goto(path);
  await ready(page);
}

/** Valor com máscara de centavos: "123456" vira R$ 1.234,56. */
export async function money(page: Page, label: string | RegExp, cents: number): Promise<void> {
  await page.getByLabel(label).fill(String(cents));
}

export async function flash(page: Page, text: string | RegExp): Promise<void> {
  await expect(page.getByRole("status").filter({ hasText: text })).toBeVisible();
}
