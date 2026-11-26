# Avisos e créditos

## 1. O que é este projeto

Social Sound: ferramenta local de narração com clonagem de voz, preparação de roteiro, legendas (SRT) e áreas de criação assistida por IA. A edição de vídeo é oferecida em um aplicativo separado.

Foi criado com ajuda de inteligência artificial (Claude, da Anthropic) e testado só em parte. É oferecido "como está", sem garantia de funcionamento, e o uso é por conta e risco de quem usa.

Não tem ligação com os projetos e empresas citados abaixo, nem com Suno, Spotify, Deezer, YouTube ou qualquer outra plataforma. A licença dos arquivos deste repositório está em [LICENSE](LICENSE) (MIT).

## 2. Programas e modelos de terceiros

Nada abaixo está dentro deste repositório. O instalador baixa direto das fontes oficiais, e cada item segue a licença própria. Não redistribua os modelos; aponte para os links oficiais.

| Item | Licença | Fonte |
|---|---|---|
| VoxCPM / VoxCPM2 (narração) | Apache-2.0 | github.com/OpenBMB/VoxCPM (confira a licença do modelo na página dele no Hugging Face) |
| PyTorch e torchaudio | BSD | pytorch.org |
| Hugging Face Hub | Apache-2.0 | github.com/huggingface/huggingface_hub |
| NumPy | BSD-3 | numpy.org |
| SoundFile | BSD-3 | pypi.org/project/soundfile |
| FastAPI | MIT | fastapi.tiangolo.com |
| Uvicorn | BSD-3 | uvicorn.org |
| python-multipart | Apache-2.0 | pypi.org/project/python-multipart |
| uv (opcional, só no Linux/macOS, para baixar o Python 3.11) | MIT / Apache-2.0 | github.com/astral-sh/uv |

**Aba Roteiro** (instalada pelo `instalar.bat`):

| Item | Licença | Fonte |
|---|---|---|
| ONNX Runtime | MIT | onnxruntime.ai |
| num2words | LGPL | pypi.org/project/num2words |
| Modelo Mark (acentos) | Apache-2.0 | huggingface.co/Mythologic/mark |

**Aba Legendas, modo Preciso** (instalada pelo `instalar.bat`):

| Item | Licença | Fonte |
|---|---|---|
| faster-whisper e CTranslate2 | MIT | github.com/SYSTRAN/faster-whisper |
| PyAV | BSD-3 | pypi.org/project/av |
| Modelos Whisper | MIT | github.com/openai/whisper |

**Interface** (já compilada em `server/web`): React (MIT), Vite (MIT), Tailwind CSS (MIT), lucide-react (ISC).

**Motores de voz opcionais** (instalados separadamente pela aba Motores de Voz; ambientes Python isolados):

| Item | Código / pesos | Observação |
|---|---|---|
| Supertonic 3 | Código MIT; pesos OpenRAIL-M | Uso comercial sujeito às restrições OpenRAIL-M; SDK Python arquivado, sem novas correções/suporte. |
| OmniVoice | Código Apache-2.0; pesos CC-BY-NC | Pesos somente não comerciais; tokenizer Higgs Audio V2 possui licença comunitária separada. |
| F5-TTS PT-BR | Código MIT; checkpoint CC-BY-NC-4.0 | Checkpoint comunitário, somente uso não comercial; não é mantido pelo projeto oficial F5-TTS. |

Leia os termos dos modelos e dos componentes auxiliares antes de instalar ou usar. Links: [Supertonic 3](https://huggingface.co/Supertone/supertonic-3), [OmniVoice](https://huggingface.co/k2-fsa/OmniVoice), [tokenizer Higgs Audio V2](https://huggingface.co/bosonai/higgs-audio-v2-tokenizer), [F5-TTS PT-BR](https://huggingface.co/Cataldir/F5-TTS-pt-br).

**IA local e runtime** (instalados sob demanda; não fazem parte do instalador base):

| Item | Licença | Fonte |
|---|---|---|
| llama.cpp | MIT | github.com/ggml-org/llama.cpp |
| Qwen3 4B Instruct Q4_K_M | Apache-2.0 | huggingface.co/Qwen/Qwen3-4B-GGUF |
| Gemma 3 4B Instruct Q4_K_M | Gemma Terms of Use | ai.google.dev/gemma/terms |

Os modelos GGUF importados pelo usuário não têm licença verificada pelo Social Sound. Confirme os termos e a procedência antes do uso. Os provedores de IA externos (OpenAI, Anthropic, Google, OpenRouter, DeepSeek, Groq e Mistral) são serviços de terceiros; suas próprias políticas, custos e termos se aplicam. As chaves API são guardadas no cofre de credenciais do sistema operacional.

**Editor de vídeo:** não faz parte do Social Sound. O projeto de edição de vídeo é separado e possui documentação e licença próprias.

## 3. Uso responsável

- Clone apenas a sua própria voz ou a de quem autorizou. Não use para enganar, imitar ou prejudicar outras pessoas.
- Se publicar vídeos com voz sintética, siga as regras de aviso de conteúdo sintético da plataforma (por exemplo, YouTube).
- Isto não é aconselhamento jurídico.

## 4. Contribuindo e compartilhando

- Compartilhe o link deste repositório. Não compartilhe a sua pasta já instalada: ela tem as suas vozes, modelos e arquivos pessoais (o `.gitignore` já evita enviá-los ao GitHub).
- Se alterar o `config.bat` com o caminho do seu computador, não envie essa alteração ao repositório.
