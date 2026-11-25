# Social Sound

Ferramenta **local** para Windows, Linux e macOS que junta, em uma janela só:

- **Roteiro**: prepara o texto para a narração (acentos, números, abreviações e pausas de respiração);
- **Narração**: gera voz com clonagem de voz (VoxCPM2);
- **Diálogo**: narração com várias vozes, uma por personagem;
- **Legendas**: gera o `.srt` (normal ou palavra por palavra) ou a lista de timestamps a partir de um áudio pronto e do roteiro;
- **IA — Roteiros e Narração**: área de criação assistida por IA (em desenvolvimento).
- **IA — Prompts Visuais**: criação de prompts para vídeos e imagens (em desenvolvimento).

Tudo roda no seu computador. A internet é usada para baixar runtime/modelos e, quando escolhidas, para conectar às APIs externas.

> Projeto criado com ajuda de inteligência artificial (Claude, da Anthropic) e testado só em parte.
> Oferecido "como está", sem garantia. Veja [AVISOS.md](AVISOS.md).

## Requisitos

- Para as novas áreas de IA: conexão à internet para baixar o runtime llama.cpp e modelos; as APIs externas exigem chave e podem gerar cobrança. As chaves são guardadas no cofre de credenciais do sistema operacional.

- Para usar as IAs locais e os provedores API, a versão atual instala também `llama.cpp` sob demanda, `httpx` e `keyring` (o cofre de credenciais do sistema).

- **Windows, Linux ou macOS** (veja a tabela abaixo)
- Python 3.11 (no Windows, marque **Add python.exe to PATH** na instalação)
- Placa NVIDIA com drivers atualizados (o modelo pede cerca de 8 GB de VRAM; se faltar, ele muda sozinho para a CPU). Sem placa NVIDIA, tudo funciona na CPU, só que bem mais devagar.
- Espaço livre em disco para os modelos (vários GB)

| Sistema | Arquivos | Observação |
|---|---|---|
| Windows | `.bat` | Sistema em que foi criado e mais testado |
| Linux | `.sh` | Placa NVIDIA usa CUDA; sem ela, usa a CPU |
| macOS (Apple Silicon ou Intel) | `.command` (duplo clique) ou `.sh` | Roda na CPU. Em Mac com Intel, o VoxCPM pode não instalar (veja abaixo) |

> Os scripts de Linux e macOS são novos e foram verificados só quanto à lógica de ligar e desligar os servidores. A instalação completa neles ainda não foi testada em máquinas reais.

## Instalação (Windows)

1. Baixe este repositório: botão verde **Code → Download ZIP** (ou `git clone`) e extraia numa pasta de fácil acesso, por exemplo `C:\SocialSound`.
2. Dê duplo clique em `instalar.bat`. Ele cria o ambiente Python e instala tudo de uma vez (motor de voz, aba Roteiro e aba Legendas) e baixa os modelos. **Demora e baixa vários GB.**

Se algum download falhar, rode o `instalar.bat` de novo: o que já foi baixado não é baixado outra vez.

## Instalação (Linux e macOS)

1. Baixe o repositório (Code → Download ZIP ou `git clone`) e extraia numa pasta, por exemplo `~/SocialSound`.
1. Abra um terminal nessa pasta e libere a execução dos scripts (só uma vez):
   ```
   chmod +x *.sh *.command
   ```
   No Mac, se o ZIP veio do navegador e o sistema bloquear os arquivos `.command` ("desenvolvedor não identificado"), rode também `xattr -dr com.apple.quarantine .` na pasta.
4. Rode `./instalar-linux.sh` (Linux). No Mac, dê duplo clique em `instalar-mac.command` — ele chama o mesmo instalador. Baixa vários GB.

**Python 3.11:** se não tiver, instale (`brew install python@3.11` no Mac; `sudo apt install python3.11 python3.11-venv` no Debian/Ubuntu). Se a sua distribuição Linux não tiver o 3.11, instale o [uv](https://docs.astral.sh/uv/): o `instalar.sh` o usa para baixar o Python 3.11 sozinho.

**Mac com Intel:** o PyTorch mais novo não existe para esse Mac. O instalador usa o 2.2.2, e o VoxCPM pode não funcionar com ele. Se falhar, a narração não é suportada nesse computador.

**Mac com chip Apple:** a narração roda na CPU por padrão. Dá para tentar a GPU do Mac com `export DEVICE=mps` no `config.sh`, mas isso não foi testado.

## Uso diário (Linux e macOS)

- **Ligar:** Linux: `./iniciar-linux.sh`. Mac: duplo clique em `iniciar-mac.command`. Os servidores rodam em segundo plano e abrem a janela com as abas no Chrome, Edge, Brave ou Chromium, se algum estiver instalado; senão, no navegador padrão. Os logs ficam na pasta `logs`.
- **Desligar:** Linux: `./parar-linux.sh`. Mac: duplo clique em `parar-mac.command`. Fechar só a janela não desliga os servidores.

## Uso diário (Windows)

- **Ligar:** duplo clique em `iniciar.bat`. Abre uma janela própria (Edge, sem barra de endereço) com a navegação lateral. Uma janela preta fica minimizada (servidor local): **não feche**.
- **Desligar:** duplo clique em `parar.bat`. Fechar só a janela do programa **não** desliga os servidores nem libera a placa de vídeo.
- **Atalhos:** `Ctrl+1` Roteiro · `Ctrl+2` Narração · `Ctrl+3` Diálogo · `Ctrl+4` Legendas · `Ctrl+5` IA Roteiros · `Ctrl+6` IA Prompts · `Ctrl+7` Fila de Narrações.
- Feche o ComfyUI (ou outro programa que use a placa) antes de ligar.

## As abas

### Roteiro
Cole o roteiro e clique em **Humanizar**. Revise as marcações: verde = acento, amarelo = número ou abreviação, azul = vírgula de respiração. Clique numa parte colorida para desfazer. Depois, **Enviar para a Narração**.

O `instalar.bat` baixa o modelo de acentos [Mark](https://huggingface.co/Mythologic/mark) (cerca de 42 MB, Apache 2.0). Ele roda na CPU e só troca acentos; não inventa nem apaga palavras. Sem o modelo, a aba usa um dicionário simples, que acerta menos.

### Narração
- Escolha uma voz padrão ou clone a sua no cartão **Clonar minha voz**.
- Escreva ou carregue um TXT/SRT, escolha o tom e gere. **BAIXAR SRT** baixa a legenda.
- Vozes padrão: criadas na primeira vez que você usa cada uma (`server\voices\_padrao`).
- Pausas: `<short pause>` = 0,5 s · `<pause 1s>` = 1 s (qualquer valor) · `<long pause>` = 1,2 s. Cada quebra de linha vira uma pausa de parágrafo (padrão 0,8 s, ajustável no painel de tom).
- Para forçar a CPU, coloque `set DEVICE=cpu` no `iniciar.bat` (Windows), antes do `start`, ou `export DEVICE=cpu` no `config.sh` (Linux/macOS).

### Divisão Inteligente de Narrações
- Abra a aba **Fila de Narrações** (atalho `Ctrl+7`) para enviar textos longos sem bloquear a tela principal.
- Escolha a voz VoxCPM2, o estilo e a duração-alvo por parte (30, 45, 60, 90 ou 120 segundos). A divisão tenta respeitar frases e nunca corta palavras; o tempo é estimado e pode variar conforme a voz e o ritmo.
- Os trabalhos são processados automaticamente, um por vez. Você pode adicionar outros textos enquanto um áudio está sendo gerado.
- Cada parte é salva separadamente e o sistema monta também o áudio completo. A fila e o histórico ficam salvos no computador.
- Para corrigir uma parte, use **Regenerar esta parte**. A nova versão fica separada para ouvir; só substitui a parte e reconstrói o áudio completo depois de clicar em **Aprovar e substituir**. Se descartar, o áudio anterior permanece.

### Diálogo
- Escreva uma fala por linha no formato `Nome: fala`. Linhas sem nome usam a voz do Narrador.
- A aba encontra os nomes sozinha; escolha uma voz (e um tom) para cada personagem. As escolhas ficam lembradas.
- Cada fala é gerada sozinha, depois tudo é juntado num áudio só, com a legenda (opcionalmente com o nome de quem fala). Pausa entre falas e entre blocos (linha em branco) ajustáveis.
- As falas não se sobrepõem. Os áudios ficam em `server\saidas` e são apagados depois de 14 dias.

### Legendas
Esqueceu de baixar o SRT? Suba o áudio pronto, cole o roteiro e a legenda sai sem refazer a narração. Use o **mesmo texto** que foi narrado (as tags de pausa são ignoradas).

- **Modo Rápido** (padrão, nada para baixar): usa as pausas do próprio áudio. Em trechos longos sem pausa, a legenda pode variar 1 a 2 s.
- **Modo Preciso**: o Whisper ouve o áudio e casa com o roteiro (melhor sincronia, mais lento). O `instalar.bat` baixa o modelo `base` (cerca de 150 MB).

Formatos:
- **Legenda normal** (`.srt`): frases quebradas pelo máximo de caracteres.
- **Palavra por palavra** (`.srt`): 1, 2 ou 3 palavras por vez, estilo Shorts/Reels. Nunca junta palavras de frases diferentes. Fica mais exata no modo Preciso.
- **Timestamps** (`.txt`): uma linha por frase com o momento em que ela começa, ex.: `[00:04] Beleza, hoje o treino é esperar.`

## Estrutura do projeto

```
social-sound/
├── instalar / iniciar / parar    .bat (Windows) · .sh e .command (Linux/macOS)
├── config.bat / config.sh        configurações opcionais
├── _comum.sh                     arquivo de apoio dos scripts
├── server/          servidor Python (FastAPI) e interface já compilada
│   ├── server.py, roteiro.py, dialogo.py, legenda.py
│   ├── web/             tela de Narração (compilada)
│   ├── estudio/         janela com abas
│   └── roteiro_web/, dialogo_web/, legenda_web/
└── web/             código-fonte da tela de Narração (React + Vite + Tailwind)
```

## Personalização

- **Logo e ícone:** troque `web\public\logo.png`, `favicon.png` e `favicon.ico`, depois rode o build (abaixo). A barra com abas usa `server\web\logo.png`.
- **Cores e fontes:** o código fica em `web\` (precisa do [Node.js](https://nodejs.org)):
  ```
  cd web
  npm install
  npm run build
  ```
  Depois copie o conteúdo de `web\dist` para `server\web`. A tela com abas fica em `server\estudio\index.html`.

## Atualizando uma versão antiga

Baixe o repositório de novo (ou `git pull`) e substitua os arquivos. Depois rode o `instalar.bat` uma vez para os complementos novos. Suas vozes (`server\voices`) continuam como estão.

## Projeto relacionado

- [Social Sound Beat](https://github.com/pedroibd/social-sound-beat): cria música a partir da letra, separa voz e instrumental e gera legendas de música. Usa a mesma placa de vídeo, então não rode os dois ao mesmo tempo.

## Créditos e licença

Código deste repositório sob licença [MIT](LICENSE). Modelos e programas de terceiros (VoxCPM2, PyTorch, Whisper etc.) são baixados direto das fontes oficiais e seguem as licenças próprias; a lista completa está em [AVISOS.md](AVISOS.md).

**Use com responsabilidade:** clone apenas a sua própria voz ou a de quem autorizou, e siga as regras de aviso de conteúdo sintético das plataformas onde publicar.

Autor: **Pedoibd** · Comunidade: [IA Voz e Vídeo no Discord](https://discord.gg/nEjHQzgz3d)
