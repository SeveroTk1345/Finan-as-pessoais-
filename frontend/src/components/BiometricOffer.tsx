"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useApi } from "@/lib/hooks";
import { type PasskeyItem, passkeySupported } from "@/lib/passkey";

// Lembrança só deste navegador; se o armazenamento falhar, o convite volta a aparecer.
const key = (userId: string) => `fin_convite_digital_${userId}`;

function readDismissed(userId: string): boolean {
  try {
    return typeof window !== "undefined" && window.localStorage.getItem(key(userId)) === "1";
  } catch {
    return false;
  }
}

/** Convite no Início para ativar digital ou rosto, quando o aparelho permite e ainda não foi ativado. */
export function BiometricOffer({ userId }: { userId: string }) {
  const [supported, setSupported] = useState(false);
  const [dismissed, setDismissed] = useState(() => readDismissed(userId));
  const list = useApi<PasskeyItem[]>(supported && !dismissed ? "/auth/digital" : null);

  useEffect(() => {
    passkeySupported().then(setSupported);
  }, []);

  if (!supported || dismissed || list.state !== "ready" || list.data.length > 0) return null;

  const dismiss = () => {
    try {
      window.localStorage.setItem(key(userId), "1");
    } catch {
      // Sem armazenamento: só esconde agora.
    }
    setDismissed(true);
  };

  return (
    <section className="card stack" aria-labelledby="convite-digital">
      <h2 id="convite-digital">Entrar sem digitar a senha</h2>
      <p>Este aparelho permite entrar com a digital ou o rosto. Quer ativar?</p>
      <div className="actions">
        <Link className="btn" href="/perfil/#digital">Ativar</Link>
        <button type="button" className="btn secondary" onClick={dismiss}>Agora não</button>
      </div>
    </section>
  );
}
