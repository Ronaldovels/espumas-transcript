# espumas-transcript

Transcreve a call do Discord de partidas de Valorant (5 stack) e aponta **poluição na comunicação**: quem fala por cima de quem, quem domina a call, callouts longos demais e ordens conflitantes.

Roda **100% local** na GPU (faster-whisper + Whisper large-v3-turbo). Nenhum áudio sai do seu PC.

## Como funciona

1. A call é gravada pelo bot **Craig** no Discord, com **um arquivo por jogador**.
2. Cada faixa é transcrita separadamente → identificação de quem falou é exata, e a sobreposição vira métrica (não erro de transcrição).
3. As faixas são juntas numa linha do tempo e o programa calcula as métricas.
4. Sai um relatório HTML + transcrição em TXT/SRT + JSON com tudo.

### O que o relatório mostra

| Métrica | O que é |
|---|---|
| **Interrupções** | Alguém começa a falar enquanto outro já está falando (≥ 0,3 s de sobreposição). "boa", "ok", "uhum" não contam. |
| **Falaram juntos** | Duas pessoas começaram ao mesmo tempo (ninguém cortou ninguém). |
| **% da fala sobreposta** | Quanto do tempo com fala teve 2+ pessoas falando. Também mede tempo com 3+ falando. |
| **Participação** | Tempo de fala de cada um e % do total — quem domina, quem some. |
| **Falas longas** | Fala ≥ 6 s ou ≥ 18 palavras (callout que poderia ser mais curto). |
| **Ordens próximas / conflito de site** | Comandos de jogadores diferentes em até 3 s; destaca quando apontam sites diferentes ("roda pro B" x "vai pro A"). |

Todos os limites são ajustáveis no `config.yaml`.

---

## Instalação (Windows, RTX série 50)

> Testado para Ryzen 7 9800X3D + RTX 5070 12 GB + 32 GB RAM. Não precisa instalar CUDA Toolkit nem ffmpeg.

1. **Driver NVIDIA atualizado** (GeForce Experience/NVIDIA App). A série 50 precisa de driver recente com suporte a CUDA 12.8+.
2. **Python 3.12** em [python.org](https://www.python.org/downloads/) — marque *Add python.exe to PATH*.
3. No PowerShell:

```powershell
git clone https://github.com/Ronaldovels/espumas-transcript
cd espumas-transcript
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy config.example.yaml config.yaml
```

4. **Teste a GPU** (baixa o modelo, ~1,6 GB, só na primeira vez):

```powershell
python -m espumas verificar -m large-v3-turbo
```

Deve aparecer `OK: modelo carregou na GPU.`

> Se o PowerShell bloquear o `Activate.ps1`, rode uma vez: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

## Gravando a partida com o Craig

1. Adicione o [Craig](https://craig.chat) ao servidor do Discord.
2. Todos na call de voz → digite `/join` antes da partida.
3. No fim, `/stop`. O Craig manda um link de download.
4. No link, baixe em **Multi-track → FLAC** (um .zip com um arquivo por pessoa).

> Use o voice do Discord, não o do Valorant — só o Discord separa as faixas.
> Avise o time que a call está sendo gravada; o Craig também anuncia isso.

## Analisando

```powershell
python -m espumas analisar "C:\Users\voce\Downloads\craig_abc123.flac.zip" -n "Ascent 13-11"
```

Saída em `saida\<nome-do-arquivo>\`:

- `relatorio.html` — abre no navegador
- `transcricao.txt` — `[12:04] Ronaldo: dois no B main`
- `transcricao.srt` — legenda para sobrepor à gravação do OBS
- `analise.json` — tudo em dados (falas, palavras com tempo, métricas)
- `cache\` — transcrições salvas; rodar de novo não retranscreve

**Mudou um limite no `config.yaml`?** Refaça só as métricas, em segundos:

```powershell
python -m espumas relatorio saida\craig_abc123.flac\analise.json
```

**Quer ver um exemplo sem gravar nada?** `python exemplos/demo.py`

### Tempo e recursos

Com a RTX 5070 o `large-v3-turbo` transcreve muito mais rápido que o tempo real; uma partida de ~40 min × 5 faixas deve levar poucos minutos (o VAD pula os silêncios, que são a maior parte de cada faixa). Usa só alguns GB dos 12 GB de VRAM.

## Melhorando a transcrição

O Whisper erra jargão. Já vem um glossário de Valorant embutido (agentes, mapas, armas, callouts) e correções comuns (`jet` → `Jett`, `espaique` → `spike`, `kill joy` → `Killjoy`...). Para o resto, no `config.yaml`:

```yaml
jogadores:          # nome do Discord -> apelido
  ronaldovels: Ronaldo
vocabulario:        # palavras que o modelo deve "conhecer"
  - Espumas
  - Kaio
correcoes:          # erros que se repetem na sua call
  "caio": "Kaio"
```

## Problemas comuns

| Erro | Solução |
|---|---|
| `CUBLAS_STATUS_NOT_SUPPORTED` | CTranslate2 antigo sem suporte à série 50: `pip install -U "ctranslate2>=4.5.0" faster-whisper` |
| `Could not load library cudnn_ops64_9.dll` / `cublas64_12.dll` | `pip install -U nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"` e rode de novo dentro do `.venv` |
| `Nenhuma GPU CUDA encontrada` | Atualize o driver NVIDIA e reinicie |
| Falta de VRAM | No config: `compute_type: int8_float16` |
| Texto inventado em silêncio ("Legendas pela comunidade Amara.org") | Já é filtrado; se aparecer outra frase recorrente, coloque em `ALUCINACOES` em `espumas/transcribe.py` |
| Sem GPU / teste rápido | `python -m espumas analisar ... --cpu` (bem mais lento) |

## Limitações

- As métricas são automáticas: **ponto de partida para revisar a call**, não veredito. Um "interrupção" pode ser um callout urgente e correto.
- Quem não usa push-to-talk pode vazar som do jogo; o VAD descarta a maior parte, mas pode sobrar fala fantasma.
- Ainda não sabe quando é round ativo, buy phase ou quem morreu.

## Próximos passos

- [ ] **Tom de voz**: emoção pelo áudio (emotion2vec) + leitura do texto por um LLM local (tilt, crítica, irritação).
- [ ] **Contexto de round**: detectar início/fim de round e mortes pela gravação do OBS → "fala de morto atrapalhando os vivos", conversa fora do jogo em round ativo.
- [ ] Classificar cada fala: callout, estratégia, conversa paralela, reclamação.
- [ ] Comparar partidas (evolução do time ao longo do tempo).

## Desenvolvimento

```powershell
pip install -r requirements-dev.txt
pytest
```

Os testes não precisam de GPU: usam áudio sintético e uma transcrição falsa.
