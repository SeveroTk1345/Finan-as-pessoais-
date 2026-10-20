import { BackLink, PageHeader } from "@/components/ui";

const TOPICS: { q: string; a: string }[] = [
  { q: "O que é “Dinheiro disponível”?", a: "É a soma do saldo das suas contas do dia a dia (conta corrente, poupança e dinheiro em espécie). O limite do cartão e os investimentos não entram, porque não são dinheiro livre para gastar." },
  { q: "O que é “Já está comprometido”?", a: "É o que vence até o seu próximo recebimento: contas a pagar (inclusive as atrasadas), faturas de cartão e parcelas de dívidas." },
  { q: "O que é “Dinheiro livre estimado”?", a: "É o dinheiro disponível menos o que já está comprometido. Se ficar negativo, o que vence passa do que você tem hoje." },
  { q: "Por que o pagamento da fatura não aparece como gasto?", a: "Porque cada compra no cartão já é contada como gasto no dia em que foi feita. Se o pagamento da fatura também contasse, o mesmo gasto seria somado duas vezes." },
  { q: "Como registro uma compra parcelada?", a: "Em Mais → Cartões, abra o cartão e use “Registrar compra”. Informe o valor total e o número de parcelas. O app distribui as parcelas nas próximas faturas." },
  { q: "Paguei só uma parte da fatura. E agora?", a: "Registre o valor pago na própria fatura. O que faltar continua aparecendo como a pagar nela. Se o banco cobrar juros na fatura seguinte, registre como “Tarifa, juros ou IOF”." },
  { q: "O banco parcelou minha fatura. Como registro?", a: "Abra a fatura e use “Parcelar esta fatura com o banco”. O valor parcelado sai da fatura, vira uma dívida em Dívidas e as parcelas aparecem nas próximas faturas." },
  { q: "Uma conta venceu e não paguei. Ela some?", a: "Não. Ela continua aparecendo como vencida até você registrar o pagamento ou cancelar." },
  { q: "Transferi dinheiro entre minhas contas. Vira receita?", a: "Não. Use “Transferir entre contas”: o dinheiro sai de uma e entra na outra sem contar como receita nem como gasto." },
  { q: "Os valores dos investimentos se atualizam sozinhos?", a: "Não. O app não busca cotações. Atualize o saldo ou o preço na tela do investimento. Valores com mais de 30 dias aparecem como desatualizados." },
  { q: "Errei um lançamento. Como corrijo?", a: "Abra o lançamento para corrigir o valor, a data ou a categoria. Também é possível cancelar: ele deixa de contar nos saldos, mas fica guardado no histórico." },
  { q: "Fiquei sem internet.", a: "Sem conexão com o servidor, o app avisa no alto da tela e não deixa salvar. Nada é perdido: quando a conexão voltar, registre de novo." },
  { q: "Esqueci minha senha.", a: "Peça para quem administra o aplicativo criar uma senha nova. Ninguém, nem o administrador, consegue ver sua senha." },
  { q: "Outra pessoa pode ver meus dados?", a: "Não pelo aplicativo: cada pessoa vê só os próprios dados. Use sempre “Sair” em aparelhos compartilhados." },
];

export default function HelpPage() {
  return (
    <div className="stack-lg">
      <BackLink href="/mais/">Mais</BackLink>
      <PageHeader title="Ajuda" subtitle="Perguntas comuns e o que significa cada valor." />
      <div className="stack">
        {TOPICS.map((t) => (
          <details key={t.q} className="card more">
            <summary>{t.q}</summary>
            <p style={{ marginTop: 8 }}>{t.a}</p>
          </details>
        ))}
      </div>
    </div>
  );
}
