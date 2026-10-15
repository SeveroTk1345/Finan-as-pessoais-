"use client";

import { type FormEvent, useState } from "react";

import { useShell } from "@/components/Shell";
import { BackLink, ErrorBox, FormError, Loading, PageHeader, Segmented, SubmitButton, TextInput } from "@/components/ui";
import { api } from "@/lib/api";
import { useApi, useSubmit } from "@/lib/hooks";
import type { Category } from "@/lib/types";

export default function CategoriesPage() {
  const { online, flash } = useShell();
  const cats = useApi<Category[]>("/categorias");
  const submit = useSubmit();
  const [kind, setKind] = useState<"despesa" | "receita">("despesa");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const ok = await submit.run((key) => api.create("/categorias", { name, kind }, key));
    if (ok) {
      flash("Categoria criada.");
      setName("");
      cats.reload();
    }
  };
  const toggle = async (c: Category) => {
    try {
      await api.patch(`/categorias/${c.id}`, { is_archived: !c.is_archived });
      cats.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro.");
    }
  };

  return (
    <div className="stack-lg">
      <BackLink href="/mais/">Mais</BackLink>
      <PageHeader title="Categorias" subtitle="Para saber com o que você gasta." />
      <Segmented label="Tipo" value={kind} onChange={setKind} options={[{ value: "despesa", label: "Despesas" }, { value: "receita", label: "Receitas" }]} />
      <FormError error={error} />
      {cats.state === "loading" ? <Loading /> : cats.state === "error" ? <ErrorBox message={cats.message} onRetry={cats.reload} /> : (
        <ul className="list">
          {cats.data.filter((c) => c.kind === kind).map((c) => (
            <li key={c.id} className="list-row">
              <span className="main"><span className="title">{c.name}</span>{c.is_archived ? <span className="sub">Escondida das listas</span> : null}</span>
              <button type="button" className="btn secondary" onClick={() => toggle(c)} disabled={!online}>
                {c.is_archived ? "Mostrar" : "Esconder"}
              </button>
            </li>
          ))}
        </ul>
      )}
      <form className="card stack" onSubmit={onSubmit} noValidate>
        <h2>Nova categoria de {kind === "despesa" ? "despesa" : "receita"}</h2>
        <FormError error={submit.error} />
        <TextInput label="Nome" value={name} onChange={setName} maxLength={40} error={submit.fields.name} />
        <SubmitButton busy={submit.busy} online={online}>Criar categoria</SubmitButton>
      </form>
    </div>
  );
}
