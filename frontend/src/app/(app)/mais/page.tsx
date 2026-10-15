import Link from "next/link";

import { PageHeader } from "@/components/ui";

const GROUPS = [
  {
    id: "grupo-dinheiro",
    title: "Seu dinheiro",
    items: [
      { href: "/contas/", label: "Contas", help: "Bancos, poupança e dinheiro em espécie" },
      { href: "/cartoes/", label: "Cartões de crédito", help: "Faturas, limite e compras parceladas" },
      { href: "/dividas/", label: "Dívidas e parcelas", help: "Empréstimos, financiamentos e renegociações" },
      { href: "/planejamento/", label: "Planejamento", help: "Metas e objetivos" },
      { href: "/planejamento/plano/", label: "Plano do mês", help: "Dividir a renda entre contas, investimento e gastos" },
      { href: "/planejamento/posso-comprar/", label: "Posso comprar?", help: "Simular uma compra antes de fazer" },
      { href: "/relatorios/", label: "Relatórios", help: "Gastos por categoria e evolução mensal" },
    ],
  },
  {
    id: "grupo-config",
    title: "Configurações",
    items: [
      { href: "/categorias/", label: "Categorias", help: "Criar e organizar categorias" },
      { href: "/perfil/", label: "Perfil e segurança", help: "Trocar a senha e sair" },
      { href: "/exportar/", label: "Exportar meus dados", help: "Baixar uma cópia em planilha" },
      { href: "/ajuda/", label: "Ajuda", help: "Como usar e o que significa cada valor" },
    ],
  },
];

export default function MorePage() {
  return (
    <div className="stack-lg">
      <PageHeader title="Mais" />
      {GROUPS.map((g) => (
        <section key={g.id} className="stack" aria-labelledby={g.id}>
          <h2 id={g.id}>{g.title}</h2>
          <ul className="list">
            {g.items.map((i) => (
              <li key={i.href}>
                <Link className="list-row" href={i.href}>
                  <span className="main">
                    <span className="title">{i.label}</span>
                    <span className="sub">{i.help}</span>
                  </span>
                  <span aria-hidden="true">›</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
