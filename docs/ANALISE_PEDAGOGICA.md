# Análise pedagógica institucional — metodologia interna 1.0

Implementação na branch dev. A aplicação é Django com templates renderizados no servidor; não há bundle SPA para compilar. O menu existente e as notificações são preservados.

## Acesso e navegação

`/instituicao/analise/` (prefixo confirmado no urls.py do projeto) reúne visão geral, aprendizagem, turmas, alunos, distratores, frequência, intervenções e, para gestão, trajetória e resultados oficiais. As entradas anteriores do professor e da gestão apontam para a mesma política central de autorização.

A instituição vem exclusivamente da conta autenticada, nunca de um parâmetro do cliente. ADMIN/MANAGER consultam os dados educacionais de sua instituição. TEACHER precisa de vínculo ativo na turma, oferta publicada e atribuição da disciplina na grade publicada. A análise de provas impressas preserva ainda a restrição anterior de emissão/autoria próprias. Responsáveis, alunos e operadores não ganham acesso ao novo módulo. As telas anteriores desses perfis não foram ampliadas.

Filtros de oferta, disciplina, avaliação, aluno, série e habilidade usam querysets autorizados. IDs adulterados são rejeitados. A mesma seleção alimenta HTML, JSON e CSV. O cadastro de evidências valida o par oferta/disciplina, aluno matriculado e publicação correspondente. Intervenções validam os mesmos vínculos para evidências anteriores e posteriores. Revisões de gabarito usam somente aplicações autorizadas. Não há cache compartilhado; as respostas usam `never_cache`.

Política histórica conservadora: turma inativa/vínculo docente removido revogam acesso do professor. Não se infere autorização a partir do compartilhamento de alunos. A gestão preserva resultados de turmas ativas sem oferta antiga vinculada, identificando a falta do código. Comparações entre professores e rankings causais não existem.

## Fontes consultadas em 13/10/2026

- Inep, catálogo de indicadores: https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/indicadores-educacionais
- Ideb: https://www.gov.br/inep/pt-br/areas-de-atuacao/pesquisas-estatisticas-e-indicadores/ideb
- Saeb: https://www.gov.br/inep/pt-br/areas-de-atuacao/avaliacao-e-exames-educacionais/saeb
- Censo: https://www.gov.br/inep/pt-br/areas-de-atuacao/pesquisas-estatisticas-e-indicadores/censo-escolar
- Taxas de rendimento: https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/indicadores-educacionais/taxas-de-rendimento-escolar
- Distorção idade-série: https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/indicadores-educacionais/taxas-de-distorcao-idade-serie
- Dicionário de indicadores: https://download.inep.gov.br/publicacoes/institucionais/estatisticas_e_indicadores/dicionario_de_indicadores_educacionais_formulas_de_calculo.pdf
- LDB: https://www.planalto.gov.br/ccivil_03/leis/l9394.htm
- BNCC, referência MEC: https://www.gov.br/mec/pt-br/escola-em-tempo-integral/BNCC_EI_EF_110518_versaofinal.pdf

Natureza: Ideb, Saeb, alfabetização e indicadores de contexto são referências oficiais importáveis. Os indicadores internos são recomendações de acompanhamento, não resultados oficiais ou exigências universais do MEC. A LDB prevê regras distintas de frequência e avaliação por etapa: os percentuais do fundamental/médio não são aplicados automaticamente à educação infantil. Na infantil, não há promoção por nota; o registro de aprovação/reprovação é bloqueado. O limiar de alerta é configurável e não é uma regra legal de aprovação.

## Dados e cálculos

| Resultado | População, cálculo e exclusões |
|---|---|
| Aproveitamento da aplicação | 100 × pontos / pontos possíveis; itens anulados excluídos; denominador zero retorna indisponível. Resultados em revisão não entram na média. |
| Reaplicação impressa | Última aplicação corrigida da mesma avaliação/turma/aluno no recorte, por emissão e ID. Uma nova avaliação é um instrumento distinto. Registros legados sem snapshot de questões preservam a contagem por aplicação, pois não permitem reconstruir versões/itens. |
| Rubrica / atividade | Última tentativa avaliada ou anulada por publicação/aluno/critério; anulação retira o critério. Pendente não apaga evidência anterior. Soma de pontos / soma dos máximos por publicação/aluno. Os pesos são os pontos máximos da rubrica. |
| Média do painel | Média dos percentuais das aplicações válidas; não é média oficial de aprovação. Sem conversão universal de conceitos em números. |
| Fontes sobrepostas | Se avaliação/aluno/oferta tiver prova impressa selecionada, rubricas da mesma avaliação ficam fora da soma para não duplicar resultados. |
| Habilidades | Contagem de itens/critérios, datas, pontos, acertos/erros objetivos e evidências qualitativas. Nenhuma classificação automática de domínio; mínimo configurável de evidências apenas para indicar insuficiência. |
| Cobertura | Objetivos cadastrados por oferta/disciplina com evidência, separando não avaliada de dificuldade. |
| Participação | Alunos com evidência / união de matrículas ativas do recorte e alunos das folhas emitidas. Não equivale à participação oficial do Saeb. Não representa presença em cada atividade. |
| Frequência | 100 × horas presentes / horas ministradas registradas, por aluno/oferta/disciplina. Zero registro é indisponível. Queda compara as duas metades cronológicas dos registros; faltas consecutivas consideram os últimos dias registrados. |
| Rendimento anual interno | Aprovação, reprovação, abandono / soma desses três estados; transferência, em curso e desconhecido separados. Continua identificado como acompanhamento interno, mesmo quando consolidado. |
| Transição interna | Promoção, repetência e evasão confirmada / soma desses estados verificados. Exige ano seguinte e fonte; não deduz evasão de falta de matrícula local. Transferência não entra no denominador. |
| Distorção interna | Dois ou mais anos acima da idade esperada / registros com nascimento, idade esperada e data de referência. Fundamental/médio apenas. Não reproduz automaticamente as populações/exclusões do Censo. |
| Distratores | Distribuição de A–E, branco e inválido; hipóteses somente com classificação revisada, com contagem de evidências. Seleção abaixo de 5% em pelo menos 20 respostas sinaliza revisão do item. |

Ausências, pendências, anulação, zero e evidência qualitativa são estados diferentes. Não há conversão de acertos em proficiência Saeb nem cálculo de Ideb com notas internas. Retenção/aplicação são registros pedagógicos com instrumento adequado justificado; não há inferência automática a partir de intervalos entre provas.

A evolução exibida é descritiva. A seleção por aluno/habilidade permite acompanhar o mesmo recorte, mas o sistema não equipara instrumentos psicometricamente. Mudanças na composição da turma podem alterar médias sem ganho de aprendizagem.

## Coleta e manutenção

Os formulários em “Metodologia, coleta e revisão” registram currículo, evidências discursivas/qualitativas, frequência em horas, intervenções, contexto da oferta e trajetória. Reutilizam conta institucional, oferta e publicação; não criam cadastro paralelo de alunos.

Indicadores oficiais permitem registro manual com instituição, código Inep validado, ano/edição, etapa, área/nível, unidade, URL oficial, metodologia, importador e data. São suportados Ideb, Saeb e distribuição por nível (uma linha por nível), participação, alfabetização, taxas de rendimento/transição/distorção, formação, regularidade/esforço docente, tamanho de turma, horas-aula, Inse e complexidade. Ausência de importação não é apresentada como prova de ausência de publicação. Existe estado explícito de não publicação confirmada. Não há download automático de planilhas oficiais.

Os dados reais precisam ser coletados ou importados pela instituição: código Inep, resultados por edição, currículo e descritores, grade publicada, presença/carga horária, rubricas, datas de nascimento, situação anual, verificação longitudinal e intervenções. Campos sem fonte não recebem números fictícios.

Metadados de distratores são opcionais no formulário de questão e copiados com a questão para a prova. O snapshot da emissão guarda alternativas, gabarito, versão, habilidades e classificação. Revisão de gabarito gera registro imutável e recalcula resultados, sem mudar o snapshot original; revisões posteriores e novas importações usam o gabarito efetivo. Histórico de alterações pedagógicas guarda antes/depois e justificativa. Provas legadas sem metadados continuam válidas, sem diagnósticos retroativos inventados.

Compartilhamento de questões mantém os controles existentes do professor/gestor. Nenhuma resposta individual é adicionada ao banco de questões.

## Demonstração, limites e operação

`seed_mock_data` continua exigindo `MOCK_PASSWORD`. O acréscimo se restringe ao Colégio Lumini Demo e usa as duas instituições, usuários e diferentes vínculos já existentes. Há habilidades avaliadas/não avaliadas, rubricas, recuperação, faltas e exemplo de resultado oficial explicitamente fictício. Não há credenciais novas fixas. A carga é idempotente.

Não há decisões automáticas de promoção/reprovação, probabilidades de evasão ou ranking de professores. O limiar de baixo rendimento deve ser configurado segundo o contexto; não existe média universal 6/7. A ferramenta não substitui o envio ao Educacenso nem valida publicações governamentais só pela URL. A gestão deve conferir a fonte e a metodologia registrada.

O HTML lista evidências e registros com paginação de 25 linhas. Agregações usam seleção do escopo antes do processamento e relações pré-carregadas. Parte da agregação dos snapshots JSON ocorre em Python; bases muito grandes exigirão materialização de itens/resultados e agregação incremental. A aplicação ainda não tem equiparação de provas, importador automático Inep, rubricas arbitrárias executáveis ou exportação dos relatórios oficiais em formato Educacenso.

Migração: `python src/manage.py migrate`. Validação: `python src/manage.py check`, `python src/manage.py makemigrations --check --dry-run`, `cd src && python manage.py test --top-level-directory=.`, `python src/manage.py collectstatic --noinput`. A entrega é exclusivamente na dev; não publica nem mescla na main.

## Evidências de validação desta entrega

- Suíte completa com descoberta correta (`cd src && python manage.py test --top-level-directory=.`): **291 testes passaram**.
- Após ampliar os casos de borda: **19 testes direcionados** de análise e carga mock passaram; após proteger a identidade das evidências, **15 testes de análise passaram**.
- Migrações aplicadas em banco local limpo, `makemigrations --check --dry-run` sem alterações pendentes, `check` sem problemas, `collectstatic` concluído e JavaScript verificado com `node --check`.
- Casos cobertos: escopo institucional e por disciplina, formatos HTML/JSON/CSV, IDs adulterados, revogação, perfis não autorizados, tentativas/anulação, denominador zero, branco/inválido, snapshots, revisão de gabarito, registro oficial, frequência, transferência, habilidades de outras disciplinas e idempotência mock.
- A descoberta padrão a partir da raiz importa alguns testes como `src.features` e falha por nomes de apps; use o comando com `--top-level-directory=.` acima.
- QA visual automatizado **não concluído**: não havia Chromium e seu download retornou arquivo inválido. Testes de resposta/renderização de templates passaram, mas não substituem inspeção visual em navegador real.
