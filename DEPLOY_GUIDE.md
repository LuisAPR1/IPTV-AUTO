# 🚀 Guia de Alojamento Gratuito Online (Deploy)

Este guia ensina como colocar o teu **IPTV Trial Generator Mobile Web App** online gratuitamente na Internet, para que possas aceder a partir de qualquer telemóvel ou computador através de um link público (ex: `https://meu-iptv-trial.onrender.com`).

---

## Opção 1: Render.com (⭐ Recomendado - Mais Fácil e 100% Grátis)

O **Render.com** oferece alojamento gratuito para aplicações Python/Flask ligando-se diretamente ao teu repositório do GitHub. Sempre que atualizares o código, o site atualiza-se sozinho!

### Passo 1: Criar Conta no Render
1. Acede a [https://render.com](https://render.com).
2. Clica em **"Sign Up"** e escolhe entrar com a tua conta do **GitHub**.

### Passo 2: Criar um Novo Web Service
1. No painel de controlo do Render (Dashboard), clica no botão azul **"New +"** (canto superior direito) e seleciona **"Web Service"**.
2. Escolhe a opção **"Build and deploy from a Git repository"** e clica em **"Next"**.
3. Procura o teu repositório: `LuisAPR1/IPTV-AUTO` (se não aparecer, clica em *Configure GitHub App* para dar permissão).
4. Clica em **"Connect"** ao lado do repositório.

### Passo 3: Configurar o Serviço
Preenche os campos conforme indicado:

| Campo | Valor a Colocar |
| :--- | :--- |
| **Name** | `iptv-trial-auto` (ou outro nome à tua escolha) |
| **Language** | `Python 3` |
| **Branch** | `main` |
| **Region** | `Frankfurt (EU)` (mais rápido para Portugal) |
| **Root Directory** | *(Deixa em branco)* |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn --chdir iptv-automatizador app:app --workers 1 --threads 8 --timeout 300` |
| **Instance Type** | **Free** ($0/month) |

### Passo 4: Adicionar Variáveis de Ambiente (Segurança)
Na mesma página, rola até à secção **"Environment Variables"** e adiciona as tuas credenciais de email para que o servidor possa ler os códigos de validação:

* **Chave 1**: `PERSONAL_GMAIL`
  * **Valor**: `o_teu_email@gmail.com`
* **Chave 2**: `GMAIL_APP_PASSWORD`
  * **Valor**: `a_tua_app_password_de_16_digitos`
* **Chave 3 (Opcional)**: `USE_PROXYSCRAPE`
  * **Valor**: `false` *(recomendado se o IP do servidor Render estiver limpo)*

### Passo 5: Iniciar o Deploy!
1. Clica no botão final **"Create Web Service"**.
2. O Render vai instalar as dependências e iniciar o servidor em cerca de 1 a 2 minutos.
3. Quando aparecer **"Live"**, o teu link público estará visível no topo (ex: `https://iptv-trial-auto.onrender.com`).

🎉 **Pronto!** Agora basta abrir esse link no teu telemóvel, clicar em **"⚡ Gerar Novo Trial 48h"** e copiar as credenciais!

---

## 📱 Dica: Criar Atalho no Telemóvel (Como se fosse uma App)

Podes transformar o link numa aplicação no ecrã principal do teu smartphone:

* **No iPhone (Safari)**: Abre o site, clica no botão de partilha (quadrado com seta para cima) e seleciona **"Adicionar ao Ecrã Principal"**.
* **No Android (Chrome)**: Abre o site, clica nos 3 pontinhos do topo e seleciona **"Adicionar ao ecrã inicial"** ou **"Instalar aplicação"**.

---

## Opção 2: Hugging Face Spaces (Alternativa 100% Gratuita)

1. Cria conta em [huggingface.co](https://huggingface.co).
2. Vai a **"New Space"**.
3. Dá um nome (ex: `iptv-trial`), escolhe **Docker** ou **Gradio/Flask**.
4. Sincroniza os ficheiros e adiciona as variáveis de ambiente em **Settings -> Variables and secrets**.

---

## 💻 Como Correr Localmente no Computador

Se quiseres usar no teu computador ou na tua rede Wi-Fi local antes de colocar online:
1. Dá duplo clique no ficheiro **`INICIAR_WEB_APP.bat`**.
2. O browser abrirá automaticamente em `http://localhost:5000`.
