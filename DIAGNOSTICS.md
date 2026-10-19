# Diagnóstico das gerações web

A aplicação guarda automaticamente as últimas **10 execuções**, incluindo sucessos, falhas e a execução em curso. Abre diretamente `/diagnostics` no endereço do site, seleciona a execução e descarrega o JSON para enviar nesta conversa. Também podes descarregar as últimas 10 de uma vez.

## Consultar os relatórios

1. Depois de publicar as alterações, abre `/diagnostics` no endereço do site.
2. A página carrega automaticamente as últimas 10 execuções, sem token nem autenticação.
3. Seleciona **Descarregar esta execução (JSON)** ou descarrega as últimas 10 e envia o ficheiro nesta conversa.

A página e as APIs de diagnóstico são de acesso livre. A ocultação dos dados sensíveis continua ativa antes da gravação. Não é necessário configurar `DIAGNOSTICS_TOKEN`; uma variável antiga com esse nome não restringe o acesso.

## O que fica no relatório

- Identificador único, estado, início/fim em UTC, duração, último passo e tentativa.
- Eventos de progresso, respostas HTTP (método, URL sem valores de parâmetros, estado e duração), procura de proxies e diagnóstico IMAP.
- Exceções com traceback, causas de tentativas falhadas e campos em falta na extração.
- Versões de Python e bibliotecas, revisão do deploy (`RENDER_GIT_COMMIT` ou `APP_VERSION`) e configuração técnica selecionada, sem segredos.

Passwords, emails, códigos, tokens, autenticação de proxies e valores dos parâmetros dos URLs são ocultados antes de gravar. Não se exportam corpos de emails, payloads HTTP, cookies nem HTML bruto. As execuções web também deixam de gerar os ficheiros legados `erros_automacao.log` e `debug_confirmation.html`; esses ficheiros antigos não são importados nem expostos.

Cada execução conserva no máximo 600 eventos, mantendo os mais recentes. O relatório indica quantos eventos foram removidos. Mensagens e tracebacks têm um limite de 12 000 caracteres. Um relatório descarregado durante a geração é uma fotografia desse momento: atualiza ou volta a descarregá-lo após o fim para obter o resultado final.

## Persistência e alojamento

O histórico usa SQLite, incluído no Python, em `iptv-automatizador/data/diagnostics.sqlite3`. Cada evento é gravado numa transação. Os ficheiros de diagnóstico estão excluídos do Git. Não são necessárias dependências novas.

Para guardar noutro local, define `DIAGNOSTICS_DB_PATH` com um caminho absoluto, por exemplo `/var/data/diagnostics.sqlite3`, numa pasta com permissão de escrita. Num serviço com disco persistente, o caminho tem de estar dentro do ponto de montagem desse disco.

**Render gratuito:** o sistema de ficheiros é efémero e pode ser perdido em reinícios, suspensão ou deploys. O histórico local não garante retenção nessas condições; descarrega o JSON antes de reiniciar ou publicar. Para conservar o histórico entre instâncias, usa armazenamento persistente. O Render permite anexar discos a serviços pagos; a alternativa arquitetural seria migrar o armazenamento para uma base de dados externa. Ver [documentação de serviços gratuitos](https://render.com/docs/free) e [discos persistentes](https://render.com/docs/disks).

Se o ficheiro sobreviver a um reinício, as execuções que estavam em curso passam a `interrupted` na primeira consulta/inicialização do histórico. A hora de fim corresponde à deteção da interrupção, não ao instante exato em que o processo parou.

Mantém **um processo/uma instância**, como nos dois `Procfile` existentes (`--workers 1 --threads 8`). A coordenação das gerações usa threads e estado em memória; SQLite não transforma o projeto numa aplicação com múltiplos workers. Para escalar, seria necessário mover os jobs para uma fila e coordenar a execução num serviço partilhado.

Se o armazenamento falhar antes do arranque, a geração devolve 503 para não iniciar uma execução sem registo. Uma falha de escrita durante a geração não interrompe a automação; o relatório avisa que pode estar incompleto e `/api/health` indica diagnóstico degradado até uma gravação voltar a funcionar. O aviso e a contagem `lost_events` ficam associados à execução na próxima gravação possível, mesmo após reinício. Uma paragem abrupta só permite recuperar o que já tinha sido gravado.

## Endpoints

| Rota GET | Conteúdo |
| --- | --- |
| `/diagnostics` | Página de consulta; não inclui os dados no HTML inicial |
| `/api/diagnostics/runs` | Resumo das últimas 10 execuções, mais recente primeiro |
| `/api/diagnostics/runs/<id>` | Uma execução com os seus eventos |
| `/api/diagnostics/export` | Download JSON das últimas 10 execuções |
| `/api/diagnostics/runs/<id>/export` | Download JSON de uma execução |

Todas as APIs desta tabela são de acesso livre e devolvem `Cache-Control: no-store`. O JSON inclui `schema_version: 1`. Uma execução removida pela retenção devolve 404. Os endpoints existentes de geração e consulta de credenciais conservam o seu modelo de acesso.

## Análise do projeto e decisões

| Área | Situação encontrada e consequência |
| --- | --- |
| `app.py` e `templates/index.html` | Flask inicia a geração numa thread e o browser consulta o progresso. O histórico só existia em memória; erros de ligação no browser podiam ficar silenciosos. Agora há registo persistido; o diagnóstico está disponível pelo URL direto, sem ligações na interface do cliente. |
| `scraper.py` | O fluxo atual usa `requests` e BeautifulSoup, com procura de proxies, checkout, verificação por email e extração. Vários erros são capturados e provocam novas tentativas; por isso é necessário conservar os logs de cada tentativa, além da falha final. |
| `email_service.py` | Uma falha de autenticação ou de rede podia acabar apresentada apenas como timeout do email. O relatório conserva a causa IMAP e o número de consultas, sem guardar conteúdo das mensagens. |
| `proxy_manager.py` | Produz eventos durante a obtenção/seleção de proxies. Os testes paralelos do scraper precisam de propagação explícita do contexto para associarem os eventos à execução certa. |
| `main.py`, `ui.py`, `window_manager.py`, `html_generator.py` | Caminho de terminal e apresentação local; não são o ponto de entrada web. O novo histórico concentra-se na geração web. |
| Configuração, scripts `.bat`, README e documentação antiga | Ainda existem referências a Playwright e ao fluxo antigo. A versão web atual usa HTTP; os dois `Procfile` já usam um worker. Esta implementação não converte os caminhos legados. |

Também foi corrigida a condição de concorrência em `/api/generate`: pedidos simultâneos reutilizam a execução ativa. O limite antigo de 300 segundos marcava o job como falhado sem parar a thread, permitindo outra geração sobreposta. O histórico mantém a execução em curso até a thread terminar ou ser detetado um reinício. Isso não introduz um mecanismo de cancelamento de threads.

## Verificação local

Na raiz do repositório:

```text
python -m unittest discover -s iptv-automatizador/tests -v
```

Os testes usam diretórios temporários e serviços simulados: não enviam emails nem criam trials. Verificam retenção, recuperação, isolamento entre threads, ocultação antes da escrita, acesso livre/exportação e os caminhos de sucesso/falha da geração web.
