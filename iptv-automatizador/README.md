# IPTV Fiesta Automatizador

> **Aplicação web atual:** o fluxo de `app.py`/`scraper.py` usa HTTP (`requests` + BeautifulSoup). Algumas instruções de terminal abaixo descrevem a versão antiga com Playwright. Para consultar e enviar os registos das últimas 10 gerações web, vê [Diagnóstico das execuções](../DIAGNOSTICS.md).

Script Python que automatiza a obtenção de trials IPTV de 48h do site myfiestatrial.com.

## Funcionalidades

- Gera email temporário automaticamente (via mail.tm)
- Preenche formulário no site
- Aguarda e extrai código de verificação do email
- Submete código e navega para página final
- Extrai credenciais: Username, Password, DNS, EPG, M3U Playlist
- Gera ficheiro HTML com os dados formatados
- Abre automaticamente no browser

## Requisitos

- Python 3.10 ou superior
- Windows (testado) / Linux / macOS

## Instalação

### 1. Instalar dependências Python

```bash
pip install -r requirements.txt
```

### 2. Instalar browsers Playwright

```bash
playwright install chromium
```

### 3. Configurar Email (Escolhe uma opção)

#### OPÇÃO A: Gmail Pessoal ⭐ RECOMENDADO

Usa a tua própria conta Gmail com plus-addressing (ex: `tua_conta+abc123@gmail.com`).

**Passos:**
1. Cria uma conta Gmail dedicada (ex: `iptv.trials@gmail.com`)
2. Ativa 2FA: https://myaccount.google.com/security
3. Gera App Password: https://myaccount.google.com/apppasswords
4. Seleciona "Mail" → Copia os 16 caracteres

**Configurar via ficheiro .env:**
```bash
# Cria ficheiro .env na pasta do projeto
PERSONAL_GMAIL=iptv.trials@gmail.com
GMAIL_APP_PASSWORD=jlil fgww weqx qknh
```

#### OPÇÃO B: RapidAPI Gmailnator (alternativo)

Usa a API do Gmailnator (free tier: 50 requests/day).

**Via environment variable:**
```powershell
$env:RAPIDAPI_KEY="2c33033d45mshf0942315474b192p189942jsn791bf52dabd6"
python main.py
```

**Obtém API key em:** https://rapidapi.com/andriimusyura/api/gmailnator

### 4. (Opcional) Tor Browser - Mudar IP Automaticamente (GRATUITO)

Se o site bloquear o teu IP, usa o **Tor Browser** - é 100% gratuito!

**Passos:**
1. Download: https://www.torproject.org/download/
2. Instala e abre o Tor Browser
3. Espera ficar verde (conectado)
4. Deixa-o a correr em background
5. Verifica se está a funcionar:
   ```bash
   python check_tor.py
   ```
6. Ativa no `.env`:
   ```
   USE_TOR=true
   ```

✅ O Tor muda o IP automaticamente a cada conexão!

### 5. Proxy Gratuito (GEO NODE) - ⭐ MAIS SIMPLES!

Para uso ocasional (1-2x/semana). Sem instalação de apps!

**Passos:**
1. Vai a https://geonode.com/free-proxy-list
2. Copia 5-10 proxies HTTP (coluna **IP:Port**)
3. Abre o ficheiro `proxies.txt` e cola os proxies (um por linha)
4. Ativa no `.env`:
   ```
   USE_PROXY_LIST=true
   ```

**Exemplo de proxies.txt:**
```
http://188.166.56.16:8080
http://203.142.82.194:8080
http://103.156.17.75:8080
```

✅ O script escolhe um proxy aleatório automaticamente!
✅ Se um falhar, tenta outro!

## Como Usar

### Execução normal (browser visível):

```bash
python main.py
```

### Modo headless (sem interface):

```bash
python main.py --headless
```

### Modo verbose (logs detalhados):

```bash
python main.py --verbose
```

### Output alternativo:

```bash
python main.py -o meu_ficheiro.html
```

## Estrutura do Projeto

```
iptv-automatizador/
├── main.py              # Script principal
├── config.py            # Configurações
├── email_service.py     # Serviço email temporário
├── scraper.py           # Automação Playwright
├── html_generator.py    # Geração HTML
├── requirements.txt     # Dependências
├── README.md           # Este ficheiro
└── trash/              # Pasta de output
    └── output.html     # Ficheiro gerado
```

## Fluxo de Execução

1. Script inicia e cria email temporário
2. Abre browser e navega para myfiestatrial.com
3. Preenche email e submete formulário
4. Aguarda código de verificação (até 120s)
5. Extrai código do email e submete no site
6. Navega para página final e extrai credenciais
7. Gera HTML em `trash/output.html`
8. Abre HTML no browser

## Troubleshooting

### Erro "playwright not found"

```bash
pip install playwright
playwright install
```

### Site bloqueia automação

- Tenta executar sem `--headless` (modo visível é menos detetável)
- O site pode ter implementado proteções adicionais

### Email não chega

- O serviço mail.tm pode estar lento
- O script tenta durante 120 segundos
- Verifica logs com `--verbose`

### Código não é extraído

- Pode ser necessário ajustar os padrões regex no `scraper.py`
- Executa com `--verbose` para ver o conteúdo da página

## Notas

- O script usa `mail.tm` para emails temporários (domínios próprios, não @gmail)
- Se o site exigir @gmail especificamente, será necessário adaptar para Gmailnator
- Browser corre em modo visível por padrão (mais fiável contra deteção)
- Dados extraídos são guardados apenas localmente

## Aviso Legal

Este script é apenas para fins educacionais. Usa de acordo com os termos de serviço do site.
