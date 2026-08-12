# Implementação do IPTV Fiesta Automatizador

## Resumo
Sistema automatizado para obter trials de 48h do IPTV Fiesta usando Playwright, com suporte a múltiplos métodos de email temporário e mudança de IP via proxy gratuito.

## Arquitetura

### Ficheiros Principais

| Ficheiro | Descrição |
|----------|-----------|
| `main.py` | Orquestrador principal, gestão de argumentos e fluxo |
| `scraper.py` | Automação Playwright do site IPTV Fiesta |
| `email_service.py` | Serviço de email (Gmail pessoal + plus-addressing) |
| `config.py` | Configurações centralizadas |
| `html_generator.py` | Geração de output HTML com credenciais |
| `proxy_manager.py` | Gestor de proxies gratuitos (lista manual) |
| `requirements.txt` | Dependências Python |
| `.env` | Variáveis de ambiente (não versionar) |

### Fluxo de Execução

```
main.py
  ↓
cria TempMailService (Gmail pessoal)
  ↓
IPTVScraper.run_automation()
  ↓
  1. Abre myfiestatrial.com
  2. Gera email (ex: conta+abc123@gmail.com)
  ↓
  3. Submete email
  4. Aguarda página de verificação
  ↓
  5. Aguarda código via IMAP
  6. Preenche código (6 inputs OTP)
  ↓
  7. Aguarda página final
  8. Extrai credenciais
  ↓
gera output HTML
  ↓
abre no browser
```

## Módulos

### 1. config.py
Configurações globais e carregamento de .env.

**Principais:**
- `PERSONAL_GMAIL` / `GMAIL_APP_PASSWORD` - Gmail com plus-addressing
- `USE_PROXY_LIST` / `PROXY_LIST_FILE` - Sistema de proxy gratuito
- `HEADLESS` - Modo visível/headless
- Timeouts e URLs

### 2. email_service.py

#### PersonalGmailService
Usa Gmail pessoal com plus-addressing (ex: `conta+abc123@gmail.com`).

**Métodos:**
- `create_inbox()` - Gera email aleatório
- `check_messages()` - Verifica IMAP por emails não lidos
- `get_verification_code()` - Aguarda e extrai código

**Requisitos:**
- Conta Gmail
- App Password (16 caracteres, não a password normal)
- IMAP ativado

#### TempMailService
Orquestrador que tenta Gmail pessoal primeiro.

### 3. scraper.py

#### IPTVScraper
Automação Playwright do site.

**Anti-detecção:**
- User agent rotativo
- Scripts anti-webdriver
- Proxy suporte

**Métodos principais:**
- `_init_browser()` - Inicializa com proxy
- `submit_email()` - Preenche formulário inicial
- `wait_for_verify_page()` - Aguarda redirecionamento
- `submit_verification_code()` - Preenche 6 inputs OTP
- `wait_for_final_page()` - Aguarda página com credenciais
- `extract_credentials()` - Extrai dados da página final

### 4. proxy_manager.py

#### SimpleProxyManager
Gestão simples de proxies gratuitos.

**Funcionamento:**
- Lê `proxies.txt` (um proxy por linha)
- Seleciona aleatório a cada execução
- Adiciona `http://` se não tiver protocolo

**Formato proxies.txt:**
```
http://188.166.56.16:8080
http://203.142.82.194:8080
```

### 5. html_generator.py
Gera HTML formatado com credenciais e botões de copiar.

## Configuração

### 1. Gmail Pessoal (Recomendado)

Criar App Password:
1. Ativar 2FA: https://myaccount.google.com/security
2. Gerar App Password: https://myaccount.google.com/apppasswords
3. Selecionar "Mail"
4. Copiar 16 caracteres

`.env`:
```
PERSONAL_GMAIL=tua_conta@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

### 2. Proxy Gratuito (Opcional)

Para mudar IP a cada execução:

1. Vai a https://geonode.com/free-proxy-list
2. Copia 5-10 proxies HTTP
3. Cola em `proxies.txt`:
```
http://188.166.56.16:8080
http://203.142.82.194:8080
```
4. Ativa no `.env`:
```
USE_PROXY_LIST=true
```

## Uso

### Execução normal:
```bash
python main.py
```

### Modo headless:
```bash
python main.py --headless
```

### Output alternativo:
```bash
python main.py -o credenciais.html
```

## Output

Gera ficheiro HTML em `trash/output.html` com:
- Username
- Password  
- M3U Playlist URL
- EPG URL
- DNS/Domain

Inclui botões "Copiar" para cada campo.

## Segurança

- `.env` não deve ser versionado (já no .gitignore)
- App Password tem acesso só a email, não à conta Google
- Proxies são gratuitos e descartáveis

## Limitações

- Gmail pessoal: limitado pela conta Gmail (pode criar conta dedicada)
- Proxies gratuitos: podem falhar, sistema tenta próximo
- Site pode bloquear após múltiplas tentativas (esperar 24h ou mudar IP)

## Troubleshooting

### "Not allowed user"
- Site detetou automatização
- Soluções: mudar IP (proxy), esperar 24h, ou usar modo headless

### Timeout no email
- Verificar se App Password está correto
- Confirmar que IMAP está ativado no Gmail
- Verificar spam/pasta promotions

### Proxy não funciona
- Testar proxy manualmente primeiro
- Tentar outro proxy da lista
- Verificar se é HTTP (não HTTPS/SOCKS)

## Dependências

- `playwright` - Automação browser
- `requests` - HTTP requests
- `beautifulsoup4` - Parsing HTML
- `python-dotenv` - Env vars

## Notas de Implementação

- Playwright: proxy deve ser configurado no `context`, não no `browser`
- Código de verificação: site usa 6 inputs separados (OTP style)
- Plus-addressing: Gmail ignora tudo depois do `+`, emails chegam à inbox principal
- IMAP: usa App Password, não a password normal da conta
