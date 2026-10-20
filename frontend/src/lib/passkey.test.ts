import { describe, expect, it } from "vitest";

import { base64urlToBytes, bytesToBase64url, guessDeviceName, passkeyErrorMessage } from "./passkey";

describe("base64url", () => {
  it("ida e volta preserva todos os bytes, inclusive os que viram + e / no base64 comum", () => {
    const all = new Uint8Array(256).map((_, i) => i);
    const text = bytesToBase64url(all);
    expect(text).not.toMatch(/[+/=]/);
    expect(Array.from(base64urlToBytes(text))).toEqual(Array.from(all));
  });

  it("decodifica sem preenchimento", () => {
    expect(Array.from(base64urlToBytes("-_8"))).toEqual([0xfb, 0xff]);
    expect(bytesToBase64url(new Uint8Array([0xfb, 0xff]))).toBe("-_8");
  });
});

describe("guessDeviceName", () => {
  it.each([
    ["Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)", "iPhone"],
    ["Mozilla/5.0 (Linux; Android 15; Pixel 9)", "Celular Android"],
    ["Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Computador Windows"],
    ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", "Mac"],
    ["algo desconhecido", "Este aparelho"],
  ])("%s", (ua, name) => {
    expect(guessDeviceName(ua)).toBe(name);
  });
});

describe("passkeyErrorMessage", () => {
  it("traduz cancelamento e aparelho já ativado", () => {
    expect(passkeyErrorMessage(new DOMException("x", "NotAllowedError"))).toMatch(/Cancelado/);
    expect(passkeyErrorMessage(new DOMException("x", "InvalidStateError"))).toMatch(/já está ativado/);
  });

  it("mantém a mensagem vinda do servidor", () => {
    expect(passkeyErrorMessage(new Error("O pedido expirou. Tente de novo."))).toBe("O pedido expirou. Tente de novo.");
  });
});
