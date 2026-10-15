"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError, checkServer, newOperationKey, onServerStatus } from "./api";

export type Loadable<T> =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ready"; data: T };

/** Busca dados da API e expõe recarregar. Ao trocar de endereço (outro mês, outro
 * registro), mostra "carregando" em vez de dado antigo; ao recarregar o mesmo
 * endereço, mantém o que já está na tela até chegar a versão nova. */
export function useApi<T>(path: string | null): Loadable<T> & { reload: () => void } {
  const [tick, setTick] = useState(0);
  const [res, setRes] = useState<{ path: string | null; tick: number; value: Loadable<T> }>({
    path: null,
    tick: -1,
    value: { state: "loading" },
  });
  useEffect(() => {
    if (path === null) return;
    let alive = true;
    api
      .get<T>(path)
      .then((data) => alive && setRes({ path, tick, value: { state: "ready", data } }))
      .catch((e: unknown) => {
        if (!alive) return;
        const message = e instanceof Error ? e.message : "Erro ao carregar.";
        setRes({ path, tick, value: { state: "error", message } });
      });
    return () => {
      alive = false;
    };
  }, [path, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  let value: Loadable<T> = { state: "loading" };
  if (res.path === path && (res.tick === tick || res.value.state === "ready")) value = res.value;
  return { ...value, reload };
}

/** Estado da conexão com o servidor (não só com a internet). */
export function useServerOnline(): boolean {
  const [online, setOnline] = useState(true);
  useEffect(() => {
    const off = onServerStatus(setOnline);
    void checkServer();
    const recheck = () => {
      if (document.visibilityState === "visible") void checkServer();
    };
    document.addEventListener("visibilitychange", recheck);
    window.addEventListener("online", recheck);
    window.addEventListener("offline", () => void checkServer());
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") void checkServer();
    }, 30000);
    return () => {
      off();
      document.removeEventListener("visibilitychange", recheck);
      window.removeEventListener("online", recheck);
      clearInterval(timer);
    };
  }, []);
  useEffect(() => {
    // Sem conexão: tenta de novo a cada 3 segundos para liberar o botão "Salvar"
    // assim que o servidor voltar a responder.
    if (online) return;
    const timer = setInterval(() => void checkServer(), 3000);
    return () => clearInterval(timer);
  }, [online]);
  return online;
}

export type SubmitState = {
  busy: boolean;
  error: string | null;
  fields: Record<string, string>;
};

/** Envio de formulário com a mesma chave de idempotência em todas as tentativas,
 * até dar certo. Campos preenchidos nunca são apagados em caso de erro. */
export function useSubmit() {
  const key = useRef<string>(newOperationKey());
  const [s, setS] = useState<SubmitState>({ busy: false, error: null, fields: {} });

  const run = useCallback(async <T,>(fn: (key: string) => Promise<T>): Promise<T | null> => {
    setS({ busy: true, error: null, fields: {} });
    try {
      const result = await fn(key.current);
      key.current = newOperationKey(); // próxima operação é outra
      setS({ busy: false, error: null, fields: {} });
      return result;
    } catch (e: unknown) {
      if (e instanceof ApiError) {
        // Erro de validação: os dados mudaram, então a próxima tentativa é outra operação.
        if (e.status === 422 || e.status === 409) key.current = newOperationKey();
        setS({ busy: false, error: e.message, fields: e.fields });
      } else if (e instanceof Error) {
        // Falha de rede: mantém a chave; reenviar não duplica se o servidor já gravou.
        setS({ busy: false, error: e.message, fields: {} });
      }
      return null;
    }
  }, []);

  return { ...s, run, setError: (error: string | null) => setS((v) => ({ ...v, error })) };
}
