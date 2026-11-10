# RAG central e MCP

O módulo ativo é `src/contexts/ia_integrations/rag/`. Chat e geração, edição e
montagem de avaliações usam este módulo. Os imports antigos do chat são somente
compatibilidade; não contêm implementações duplicadas. Os esboços desconectados
`features/assessments/rag_service.py` e `montage_service.py` foram substituídos.

| Arquivo | Responsabilidade |
|---|---|
| `service.py` | Selecionar o provedor; API `complete` / `acomplete` |
| `providers/ollama.py` | Inferência local, streaming, timeout e cancelamento |
| `providers/mcp.py` | Cliente MCP Streamable HTTP para inferência remota |
| `orchestrator.py` | Contexto, histórico limitado, consultas e proposta validada |
| `retrieval.py` | Busca no manual e leitura dos dados autorizados |
| `actions.py` | Validação e gravação transacional das propostas confirmadas |
| `mcp_server.py` | Ferramentas de leitura do banco de questões |
| `auth.py` | Credenciais por usuário, expiração e revalidação |

A recuperação atual usa busca textual no manual e consultas ao banco com controle
de acesso. Não há embeddings, banco vetorial ou treinamento de modelo.

## Escolha do provedor

O padrão continua local:

```dotenv
RAG_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:0.5b
```

No Compose a URL do Ollama é `http://ollama:11434`. Para um serviço remoto:

```dotenv
RAG_PROVIDER=mcp
RAG_MCP_URL=https://seu-servico.example/mcp
RAG_MCP_TOKEN=credencial-do-servico
RAG_MCP_TOOL=complete
RAG_MCP_TIMEOUT_SECONDS=180
IA_CHAT_TIMEOUT_SECONDS=240
RAG_QUESTIONS_MCP_URL=https://seu-aplicativo.example/mcp/questions
```

As URLs acima são exemplos; configure o serviço real. O módulo não pressupõe um
fornecedor específico, mas o servidor externo precisa implementar o contrato
abaixo. MCP transporta ferramentas; não é por si só um modelo de linguagem.
Não aponte `RAG_MCP_URL` para o endpoint de questões: ele não faz inferência.
Use HTTPS fora da rede local. Só configure serviços confiáveis: eles recebem o
contexto necessário para responder e, quando habilitado, acesso temporário às
questões disponíveis ao usuário. Nenhum endereço vem do texto enviado ao modelo.

```bash
docker compose up -d --build web
```

Não há migração de banco nem necessidade de apagar volumes. Para usar apenas
inferência remota, os serviços Ollama podem ficar parados. O endpoint MCP de
questões roda no mesmo processo ASGI de `web`; não exige outro container.

## Contrato do serviço de inferência MCP

SDK Python oficial 1.x, Streamable HTTP, com negociação `initialize` e `tools/call`.
A ferramenta configurada recebe:

```json
{"messages":[{"role":"system","content":"..."},{"role":"user","content":"..."}],"structured":true}
```

Retorne o objeto JSON pedido em `structuredContent`, ou um único JSON nos blocos
`TextContent`. Para chat, normalmente `{"message":"...","proposal":null}`; para
montagem, `{"question_ids":[1,2]}` ou o esquema solicitado nas mensagens. O
serviço deve seguir o esquema de cada chamada, não responder sempre com um
objeto de chat. Erros devem marcar `isError=true`.

O chat permite até duas consultas locais por mensagem retornando
`{"tool":{"name":"search_questions","query":"frações"}}`, ou `get_question`
com `id`, antes da resposta final. Essa opção funciona com ambos os provedores.
A geração direta de avaliações pede o JSON final e não executa esse ciclo de
consultas. Para consultar mais questões nesse fluxo, o serviço remoto usa o
MCP de questões descrito abaixo.

Se `RAG_QUESTIONS_MCP_URL` estiver preenchida, a chamada também inclui metadados
MCP `_meta["lumini/questions"]` com `url`, `bearer_token` e `expires_in=300`.
O servidor externo deve usar esse token no header `Authorization: Bearer ...`
do cliente MCP de questões. Não inclua os metadados no prompt do modelo, nas
respostas ou nos logs. O token é emitido para o usuário autenticado da operação;
o modelo não escolhe um `user_id`. Sem essa URL, o ciclo de consultas locais do
chat continua disponível, mas não há acesso MCP direto pelo serviço externo.

O adaptador remoto entrega a resposta completa; não simula streaming de tokens.
Ollama mantém streaming. Ambos respeitam cancelamento e prazo; propostas só são
aceitas depois da validação. Não existe fallback automático para outro provedor.

## MCP de questões

Endpoint: `/mcp/questions`, autenticado por Bearer, sem sessão de navegador.

| Ferramenta | Argumentos | Resultado |
|---|---|---|
| `search_questions` | `query_text` opcional, até 160 caracteres | Até 30 questões acessíveis; enunciados abreviados |
| `get_question` | `question_id` inteiro | Conteúdo, alternativas, gabarito, metadados pedagógicos e versão |
| `get_questionnaire` | `questionnaire_id` inteiro | Questionário próprio e até 30 questões |

O modelo pode consultar essas ferramentas para escolher IDs existentes ou ler
uma questão antes de propor sua edição. Não há ferramenta MCP que escreva no
banco. No chat, a proposta aparece para confirmação; ao salvar, permissões e
versões são revalidadas. Uma edição cria uma nova versão da questão. Os botões de
IA já existentes nas avaliações continuam usando seus fluxos de gravação.

As permissões são as mesmas de `available_questions(user)` e das avaliações
próprias. Contas inativas, troca obrigatória de senha, credenciais expiradas ou
alteradas são rejeitadas. Trocar a senha invalida tokens emitidos anteriormente.
O endpoint valida `DJANGO_ALLOWED_HOSTS` e rejeita requisições com `Origin`:
esta integração é entre servidores, não acesso JavaScript direto do navegador.

Para testar com um cliente MCP externo administrado por você, emita uma credencial
curta no servidor (não é uma chave global nem credencial permanente):

```bash
python src/manage.py issue_rag_token --user-id 123
```

Use a saída como Bearer por até cinco minutos. O provedor MCP emite e encaminha
essa credencial automaticamente nas chamadas, quando a URL de questões está
configurada. Não há mecanismo OAuth de conexão interativa neste endpoint.

## Verificação

```bash
python src/manage.py test contexts.ia_integrations.rag.tests contexts.ia_integrations.features.chat_bot.tests --noinput
```

Os testes usam o SDK e transporte HTTP ASGI reais, com banco de testes, incluindo
negociação, descoberta, consultas, isolamento, credenciais, seleção do provedor,
timeout e cancelamento. O serviço remoto de inferência é um servidor de teste;
a configuração de um fornecedor e sua inferência real precisam ser verificadas
no ambiente de implantação.

Referência: [SDK MCP oficial, versão 1](https://py.sdk.modelcontextprotocol.io/v1/).

## Modos do chat

Os botões **Montagem** e **Dúvidas** no topo do chat enviam `mode=assembly` ou
`mode=doubts` junto de `chat.message`. Dúvidas é o padrão para clientes antigos.
O servidor valida o modo; a escolha não depende de inferência do modelo.

- Dúvidas: manual pertinente e consultas de desempenho; sem esquemas de criação,
  propostas graváveis ou credencial MCP de questões.
- Montagem: esquemas de questões/questionários e consultas ao banco; sem manual
  nem instruções das análises institucionais.

O histórico continua salvo e visível, mas somente mensagens marcadas com o mesmo
modo são enviadas ao modelo. Mensagens anteriores a esta divisão, sem marcação,
continuam visíveis e não entram no contexto. Recarregar restaura o modo da última
mensagem. Durante uma resposta, os botões ficam desabilitados para evitar trocar
o modo de uma solicitação em andamento. Sugestões selecionam seu modo correspondente.
