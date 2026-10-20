import { BackLink, PageHeader } from "@/components/ui";

export default function ExportPage() {
  return (
    <div className="stack-lg">
      <BackLink href="/mais/">Mais</BackLink>
      <PageHeader title="Exportar meus dados" subtitle="Baixe uma cópia só dos seus dados." />
      <section className="card stack">
        <h2>Planilha de lançamentos</h2>
        <p className="muted">Arquivo para abrir no Excel ou no Google Planilhas, com todas as suas receitas, despesas e transferências.</p>
        <a className="btn" href="/api/exportar/lancamentos.csv" download>Baixar planilha (CSV)</a>
      </section>
      <section className="card stack">
        <h2>Cópia completa</h2>
        <p className="muted">Todos os seus dados (contas, cartões, dívidas, investimentos e metas) em um arquivo técnico.</p>
        <a className="btn secondary" href="/api/exportar/dados.json" download>Baixar cópia completa (JSON)</a>
      </section>
      <p className="small muted">
        Os arquivos ficam no aparelho onde você baixar. Em aparelho compartilhado, apague-os depois de usar.
      </p>
    </div>
  );
}
