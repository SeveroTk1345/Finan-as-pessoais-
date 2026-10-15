# Privacidade e segurança

Documento para as três pessoas que usam o aplicativo (decisão P3).

## O que fica onde

| Onde | O quê |
|---|---|
| **Servidor** (banco PostgreSQL) | Todos os dados financeiros de cada pessoa, separados por dono; o resumo cifrado (hash Argon2) da senha; sessões abertas (só o hash do código da sessão); tentativas de login do último dia; para quem ativou a digital ou o rosto, a **chave pública** de cada aparelho (não serve para entrar sozinha e não contém nada da biometria) |
| **Cópias de segurança** (no servidor) | Uma cópia do banco inteiro por dia, guardadas por 14 dias |
| **iPhone ou computador** | A digital ou o rosto ficam **só no aparelho**, guardados pelo próprio sistema (como no desbloqueio da tela); o app nunca os recebe. Além disso, só a estrutura do aplicativo (telas, ícones, fonte) e um cookie de sessão que o JavaScript não consegue ler. **Nenhum dado financeiro fica guardado no aparelho**; arquivos exportados ficam onde você os baixar |
| **Serviços externos** | Nenhum dado financeiro é enviado para fora do servidor. Não há integração com bancos, inteligência artificial ou análise de uso |

## Quem vê o quê

* **Pelo aplicativo:** cada pessoa vê, altera e exporta **somente os próprios dados**. Isso é garantido em duas camadas (verificação na aplicação e regra do próprio banco de dados) e testado automaticamente com tentativas de acesso cruzado entre as três contas.
* **Não existe conta de administrador** que veja as finanças de outra pessoa pelo aplicativo.
* **Quem administra o servidor** (o Diogo) tem acesso técnico ao banco e às cópias de segurança, como em qualquer sistema hospedado. O compromisso é não consultar dados de outra pessoa e usar esse acesso só para manutenção (atualizar, fazer backup, restaurar, redefinir senha a pedido). Uma alternativa que impediria até esse acesso (criptografia de ponta a ponta) foi avaliada e descartada: impediria os cálculos e a recuperação de senha.

## Proteções implementadas

* Entrar com digital ou rosto (opcional): padrão WebAuthn, o mesmo de bancos e grandes serviços. Cada entrada assina um desafio novo, que só vale uma vez e só para o endereço do app; um site falso não consegue usar a resposta. Na tela **Perfil e segurança** dá para ver os aparelhos ativados e remover qualquer um.
* Senhas com Argon2id; mínimo de 10 caracteres; bloqueio por 15 minutos após 5 tentativas erradas por usuário (ou 20 por endereço).
* Sessão expira: sem "Manter conectado", após 30 minutos sem uso ou 12 horas; com a opção, após 7 dias sem uso ou 30 dias.
* "Sair" encerra a sessão no servidor; voltar pelo navegador não mostra dados.
* Cookie `HttpOnly`, `Secure` (HTTPS) e `SameSite=Strict`; requisições de outros sites são recusadas.
* Banco sem porta exposta na internet; só HTTPS (com HSTS) aberto ao público.
* Respostas da API não ficam em cache no navegador.
* Registros financeiros não são apagados: cancelamentos e edições ficam no histórico.
* Logs registram só o tipo do erro e a rota, nunca valores ou descrições.
* Exportação em planilha protegida contra fórmulas maliciosas no Excel.

## Limitações honestas

* A segurança depende também do servidor estar atualizado e das senhas não serem compartilhadas.
* Nenhuma auditoria de segurança externa foi feita.
* Quem souber o PIN de desbloqueio do seu celular também passa pela "digital ou rosto", porque o próprio aparelho aceita o PIN como alternativa. Não compartilhe o PIN do celular.
* As cópias de segurança ainda não são cifradas nem copiadas para fora do servidor (pendência D9).
