# Validação no iPhone (roteiro manual)

**Situação:** ainda **não executado**. Os testes automáticos rodam no Chromium com tela e perfil de iPhone, não no Safari real. Este roteiro deve ser feito no iPhone físico depois da publicação (`IMPLANTACAO.md`). Marque cada item e anote problemas em `REGISTRO_TESTES.md`.

## Instalação
- [ ] Safari abre o endereço com cadeado (HTTPS válido)
- [ ] Login funciona; mensagem clara com senha errada
- [ ] "Adicionar à Tela de Início" mostra o ícone preto com "R$" e o nome "Finanças"
- [ ] O app abre pelo ícone sem a barra do Safari, respeitando o entalhe e a barra inferior
- [ ] Pede login pelo ícone na primeira vez (comportamento esperado do iOS)

## Uso
- [ ] Campo de valor abre o teclado numérico; "4590" vira R$ 45,90
- [ ] Campo de data abre o seletor do iOS; abaixo aparece "Data escolhida: DD/MM/AAAA"
- [ ] Registrar despesa, receita e transferência; mensagem "✓ … salva" aparece
- [ ] Contas a pagar: cadastrar, pagar em parte, ver como vencida
- [ ] Cartão: compra parcelada, pagar fatura
- [ ] Dívida: pagamento; investimento: aporte e atualização de saldo
- [ ] Nenhuma tela com rolagem para o lado
- [ ] Texto ampliado (Ajustes → Tela e Brilho → Tamanho do Texto) e zoom com dois dedos funcionam
- [ ] VoiceOver lê rótulos dos campos e botões

## Conexão
- [ ] Modo Avião: aparece o aviso preto "Sem conexão com o servidor"; botão Salvar desabilitado
- [ ] Ao voltar a conexão, o aviso some em poucos segundos e o salvamento funciona
- [ ] Fechar o app e reabrir: dados continuam lá

## Privacidade
- [ ] Sair → botão voltar não mostra dados
- [ ] Outra pessoa entra no mesmo iPhone e não vê dados da anterior
- [ ] Após 30 minutos sem uso (sem "Manter conectado"), pede login de novo

## Atualização
- [ ] Depois de publicar uma versão nova, aparece "Nova versão disponível · Atualizar"
