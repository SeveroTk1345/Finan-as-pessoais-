"use client";

import { useEffect, useState } from "react";

/** Registra o service worker e avisa quando houver versão nova do aplicativo. */
export function ServiceWorker() {
  const [waiting, setWaiting] = useState<ServiceWorker | null>(null);

  useEffect(() => {
    if (!("serviceWorker" in navigator) || process.env.NODE_ENV !== "production") return;
    let reloaded = false;
    // Na primeira visita o service worker assume a página sem mudar nada nela:
    // recarregar aí apagaria o que a pessoa já digitou. Só recarrega em atualização.
    const hadController = Boolean(navigator.serviceWorker.controller);
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (reloaded || !hadController) return;
      reloaded = true;
      window.location.reload();
    });
    navigator.serviceWorker.register("/sw.js").then((reg) => {
      if (reg.waiting && navigator.serviceWorker.controller) setWaiting(reg.waiting);
      reg.addEventListener("updatefound", () => {
        const sw = reg.installing;
        sw?.addEventListener("statechange", () => {
          if (sw.state === "installed" && navigator.serviceWorker.controller) setWaiting(sw);
        });
      });
      const check = () => document.visibilityState === "visible" && reg.update().catch(() => undefined);
      document.addEventListener("visibilitychange", check);
    }).catch(() => undefined);
  }, []);

  if (!waiting) return null;
  return (
    <div className="offline-bar" role="status" style={{ display: "flex", gap: 12, alignItems: "center", justifyContent: "center", flexWrap: "wrap" }}>
      Nova versão disponível.
      <button type="button" className="btn secondary" style={{ minHeight: 44 }} onClick={() => waiting.postMessage("SKIP_WAITING")}>
        Atualizar
      </button>
    </div>
  );
}
