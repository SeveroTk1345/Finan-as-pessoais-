import { existsSync } from "node:fs";

import { defineConfig, devices } from "@playwright/test";

// Usa o Chromium já instalado no ambiente, se houver; senão, o baixado pelo Playwright.
const chromium = process.env.PW_CHROMIUM ?? "/opt/pw-browsers/chromium";

// Roda contra a pilha completa subida por scripts/stack-local.sh (FIN_E2E_URL).
// Navegador: Chromium com perfil e tela de iPhone. Não é o Safari real: a validação
// no iPhone físico está no roteiro manual de docs/VALIDACAO_IPHONE.md.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: [["list"]],
  use: {
    baseURL: process.env.FIN_E2E_URL ?? "http://127.0.0.1:8765",
    locale: "pt-BR",
    timezoneId: "America/Sao_Paulo",
    trace: "retain-on-failure",
    launchOptions: existsSync(chromium) ? { executablePath: chromium } : {},
  },
  projects: [{ name: "iphone", use: { ...devices["iPhone 13"], browserName: "chromium" } }],
});
