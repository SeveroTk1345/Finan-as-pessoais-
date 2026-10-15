# Acessibilidade e usabilidade

**Limitação:** não foi possível fazer testes com usuários reais (pessoas de cerca de 60 anos) neste ambiente. Em vez disso, foi feita uma revisão estruturada e há verificações automáticas. O teste com usuários (tarefa T6.3) continua pendente e é recomendado antes do uso definitivo.

## Verificações automáticas (Playwright, perfil iPhone SE e iPhone 13)
* Nenhuma rolagem horizontal em 15 telas principais na largura de 320 px.
* Todos os botões, campos e itens do menu com altura de pelo menos 44 px (o padrão visual usa 48 px).
* Texto-base de 18 px.
* Todo campo visível de formulário tem rótulo associado.
* Tela de login sem nenhum valor financeiro.

## Revisão estruturada (checklist)
| Item | Situação |
|---|---|
| Contraste: texto principal #111 e secundário #4a4a4a sobre branco (acima de 7:1); verde #11643a e vermelho #a1161c acima de 7:1 | Atende |
| Cor nunca é o único indicador: situações usam texto ("Vencida", "Paga"); valores negativos têm sinal "-" | Atende |
| Foco visível (contorno preto de 3 px) em todos os elementos interativos | Atende |
| Rótulos sempre visíveis acima dos campos (não somem ao digitar) | Atende |
| Erros explicam o problema e como corrigir; os campos preenchidos não são apagados | Atende |
| Confirmação antes de cancelar, excluir e desativar | Atende |
| Mensagem de sucesso após salvar ("✓ Despesa salva.") | Atende |
| Ícones sempre com texto ao lado | Atende |
| Zoom do navegador permitido (sem bloqueio no viewport) | Atende |
| Respeita "reduzir movimento" | Atende |
| Telas vazias explicam o que fazer | Atende |
| Linguagem cotidiana ("Dinheiro disponível", "Quanto devo") | Atende |
| Campos opcionais escondidos em "Mais detalhes" para formulários curtos | Atende |
| Link "Pular para o conteúdo" para leitores de tela | Atende |
| Gráficos sempre com valores em texto ou tabela | Atende |

## Pontos de atenção para o teste com usuários
* A navegação no celular tem 5 itens; Contas, Cartões e Dívidas ficam em "Mais". Observar se as pessoas encontram.
* O campo de valor com máscara (números entram pela direita) é comum em apps de banco, mas vale confirmar se é entendido.
* Termos como "fatura fechada" e "parcelamento de fatura" têm explicação em Ajuda; observar se precisam aparecer na própria tela.
