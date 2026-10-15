/** Cenário 12 (tela pequena) e verificações de acessibilidade básicas. */
import { devices, expect, test } from "@playwright/test";

import { login, open } from "./helpers";

const PAGES = [
  "/", "/contas/", "/lancamentos/", "/lancamentos/novo/?tipo=despesa", "/a-pagar/", "/a-pagar/nova/", "/cartoes/",
  "/dividas/", "/investimentos/", "/planejamento/", "/relatorios/", "/mais/", "/categorias/", "/perfil/", "/ajuda/",
];

test.use({ ...devices["iPhone SE"], browserName: "chromium" });

test("12. tela pequena: sem rolagem horizontal e alvos de toque grandes", async ({ page }) => {
  await login(page, "carla");
  for (const path of PAGES) {
    await open(page, path);
    await page.waitForTimeout(300);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, `rolagem horizontal em ${path}`).toBeLessThanOrEqual(0);
    const small = await page.evaluate(() =>
      Array.from(document.querySelectorAll<HTMLElement>(".btn, input.input, select.input, .bottombar a"))
        .filter((el) => el.offsetParent !== null)
        .map((el) => ({ text: (el.innerText || el.getAttribute("aria-label") || el.id).slice(0, 30), h: el.getBoundingClientRect().height }))
        .filter((x) => x.h < 44),
    );
    expect(small, `alvos pequenos em ${path}`).toEqual([]);
    const fontSize = await page.evaluate(() => Number(getComputedStyle(document.body).fontSize.replace("px", "")));
    expect(fontSize).toBeGreaterThanOrEqual(18);
  }
});

test("todo campo de formulário tem rótulo visível", async ({ page }) => {
  await login(page, "carla");
  for (const path of ["/lancamentos/novo/?tipo=despesa", "/a-pagar/nova/", "/contas/nova/", "/dividas/nova/", "/investimentos/novo/", "/perfil/"]) {
    await open(page, path);
    const unlabeled = await page.evaluate(() =>
      Array.from(document.querySelectorAll<HTMLInputElement>("input:not([type=hidden]), select, textarea"))
        .filter((el) => el.offsetParent !== null)
        .filter((el) => !(el.labels && el.labels.length > 0) && !el.closest("label"))
        .map((el) => el.outerHTML.slice(0, 80)),
    );
    expect(unlabeled, `campos sem rótulo em ${path}`).toEqual([]);
  }
});

test("tela de login não mostra dados financeiros e cabeçalhos protegem a API", async ({ page }) => {
  await open(page, "/entrar/");
  await expect(page.getByText("R$")).toHaveCount(0);
  const res = await page.request.get("/api/resumo");
  expect(res.status()).toBe(401);
  expect(res.headers()["cache-control"]).toBe("no-store");
});
