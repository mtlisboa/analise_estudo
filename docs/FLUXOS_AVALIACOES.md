# Organização de Avaliações

A navegação lateral possui apenas Banco de questões e Questionários. Correções fica na navegação de topo da área de Questionários, com entregas online, gabaritos para revisão e solicitações de gabaritos de aplicações físicas finalizadas ou com prazo vencido.

## Banco

Públicas reúne o banco da instituição e conteúdos disponibilizados com autorização. Privadas reúne somente questões próprias não compartilhadas. As linhas mostram título e metadados, e a prévia completa abre em modal. A lista usa carregamento incremental com cursor, rolagem infinita e botão de fallback. As regras de acesso também são verificadas nas prévias e na seleção.

## Questionários

Criar questionário abre um editor único: título, disciplina, formato (impresso ou área do aluno), prazo obrigatório, questões selecionadas em modal, turmas e visibilidade. O mesmo editor abre pelos módulos da turma, com disciplina e turma pré-selecionadas. Ocultar retira a publicação dos alunos; disponibilizar publica e notifica. Questionários impressos visíveis geram emissões identificadas para as turmas selecionadas e bloqueiam o envio online de respostas.

Finalizar aplicação física coloca os gabaritos faltantes na página Correções. Os atalhos permitem fotografar, importar e revisar. Aplicações anteriores, questões e correções continuam preservadas. A migração recupera visibilidade e prazo das publicações anteriores.

---

# Avaliações online e impressas

## Montagem

Em Avaliações > Banco de questões, crie os itens e marque as questões desejadas. Escolha uma avaliação existente ou deixe a seleção vazia e informe o título para criar uma avaliação da mesma disciplina. O botão Montar avaliação e continuar leva o professor à aplicação nas turmas. O editor mantém atalhos para selecionar mais questões, aplicar nas turmas ou imprimir.

## Aplicação online

Selecione uma ou mais ofertas publicadas da disciplina nas quais o professor tem vínculo ativo. Aplicar e notificar publica uma cópia do conteúdo para cada turma. As notificações possuem um link para a atividade; a atividade também aparece nos módulos da turma e da disciplina.

O aluno responde alternativas e questões abertas e envia uma única entrega. Há validação de prazo, matrícula, alternativas e versão da atividade. As alternativas recebem pontuação automática; questões abertas ficam pendentes. O professor abre a entrega na publicação ou em Correções pendentes, atribui pontos e conclui. Cada revisão guarda os pontos anteriores e o responsável.

O gabarito fica em um snapshot privado separado do conteúdo do aluno. Depois da primeira entrega, alterações de conteúdo/gabarito exigem uma nova avaliação/aplicação. Publicações antigas sem gabarito histórico registrado aceitam respostas, mas todas as questões exigem correção manual; o sistema não utiliza o gabarito atual para adivinhar a versão antiga.

## Aplicação impressa

Em Imprimir e corrigir, emita para uma turma da disciplina. Baixe as provas completas da turma ou a prova individual ao lado do aluno. O PDF contém a folha de bolinhas e as páginas das questões, com identificação e QR assinado em cada página. A emissão preserva questões, imagens, pontos, gabarito e identificação. Questões abertas têm linhas para resposta e são corrigidas manualmente.

Em Fotografar prova, use a câmera do celular (quando suportada pelo navegador) ou selecione uma imagem JPG/PNG. O QR identifica a emissão e o aluno; a autorização do professor é verificada antes de anexar. Fotografe a folha completa, com os quatro marcadores, e depois as páginas das respostas abertas. As páginas podem chegar em qualquer ordem. O resultado só surge após importar a folha de bolinhas.

Os envios por PDF, ZIP e CSV continuam disponíveis por emissão. No CSV, A–E representam alternativas e as colunas de questões abertas aceitam texto; a nota dessas questões continua sendo manual. Uma página ou resultado duplicado é preservado, sem sobrescrita. Marcações ambíguas exigem revisão; páginas com QR inválido não são atribuídas a ninguém.

## Implantação e validação

Executar as migrações (o entrypoint já faz isso) e instalar as dependências atualizadas, incluindo pypdf. Os testes cobrem publicação, notificação, acesso pela turma, envio, correção, seleção de várias turmas, PDF misto, QR, câmera, OMR, páginas fora de ordem e controles de acesso. A validação automática usa PDFs rasterizados e imagens transformadas; fotos reais de celulares ainda precisam de validação em campo.

## Inclusão de conteúdo na turma

O professor com vínculo institucional e matrícula ativa de professor pode gerenciar sua turma sem depender da marcação legada de professor no vínculo organizacional. Na disciplina publicada, há controles para adicionar atividade/prova e enviar um módulo PDF diretamente pela sala. Rascunhos próprios aparecem para o professor, mas permanecem ocultos aos alunos. A criação pela turma pré-seleciona a disciplina, a turma e a visibilidade; o professor pode desmarcar a visibilidade para salvar um rascunho. PDFs aparecem tanto na turma quanto na disciplina do aluno, com leitor integrado e opção de outra guia.
