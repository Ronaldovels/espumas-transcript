# espumas-transcript

Transcreve a call do Discord de partidas de Valorant (5 stack), cruza com os dados da partida e aponta **poluição na comunicação**: quem fala por cima de quem, quem fala depois de morrer, quem domina a call, callouts longos e ordens conflitantes.

A transcrição roda **100% local** na GPU (faster-whisper + Whisper large-v3-turbo). O áudio não sai do seu PC; só os dados da partida vêm da internet (HenrikDev API).

## Como funciona

1. A call é gravada pelo bot **Craig** no Discord, com **um arquivo por jogador**.
2. Cada faixa é transcrita separadamente: a identificação de quem falou é exata, e a sobreposição vira métrica (não erro de transcrição).
3. A partida é buscada na **HenrikDev API** (não oficial): rounds, kills, mortes, plant e defuse com horário.
4. A gravação é **sincronizada** com a partida pela palavra **"espumas"** falada na call (ver abaixo).
5. Sai um relatório com tudo cruzado, mais transcrição em TXT/SRT e um JSON.

### O que o relatório mostra

| Métrica | O que é |
|---|---|
| **Interrupções** | Alguém começa a falar enquanto outro já está falando (≥ 0,3 s de sobreposição). "boa", "ok", "uhum" não contam. |
| **% da fala sobreposta** | Quanto do tempo com fala teve 2+ pessoas falando. Também mede tempo com 3+ falando. |
| **Participação** | Tempo de fala de cada um e % do total. |
| **Fala de morto** | Falar depois de morrer enquanto alguém do time ainda está vivo, e quantas vezes foi **por cima da fala de um vivo**. |
| **Por round** | Resultado, kills, mortes, fala no round, interrupções e fala de morto de cada round. |
| **Ganhos x perdidos** | Média dessas métricas em rounds ganhos contra perdidos. |
| **Quando a call falou** | % da fala na compra, no round ativo e no fim de round. |
| **Falas longas** | Fala ≥ 6 s ou ≥ 18 palavras. |
| **Ordens conflitantes** | Comandos de jogadores diferentes em até 3 s, destacando sites diferentes ("roda pro B" x "vai pro A"). |

A linha do tempo mostra uma linha por round, com compra em cinza, kills (▲) e mortes (▼) do time, plant/defuse e as falas de cada um.

---

## Instalação (Windows, RTX série 50)

> Feito para Ryzen 7 9800X3D + RTX 5070 12 GB + 32 GB RAM. Não precisa instalar CUDA Toolkit nem ffmpeg.

1. **Driver NVIDIA atualizado** (NVIDIA App). A série 50 precisa de driver com suporte a CUDA 12.8+.
2. **Python 3.12** em [python.org](https://www.python.org/downloads/), marcando *Add python.exe to PATH*.
3. No PowerShell:

```powershell
git clone https://github.com/Ronaldovels/espumas-transcript
cd espumas-transcript
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

4. **Teste a GPU** (baixa o modelo, ~1,6 GB, só na primeira vez):

```powershell
python -m espumas verificar -m large-v3-turbo
```

Deve aparecer `OK: modelo carregou na GPU.`

> Se o PowerShell bloquear o `Activate.ps1`, rode uma vez: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

5. **Chave da HenrikDev API**: gratuita, pedida no Discord da HenrikDev (veja [docs.henrikdev.xyz](https://docs.henrikdev.xyz)). Sem ela o programa funciona, mas só analisa a call, sem rounds e mortes.

## Usando a interface

Dê dois cliques em **`iniciar.bat`**. O navegador abre em `http://127.0.0.1:8765` (só no seu PC).

1. Em **Configurações**, cole a chave da HenrikDev e seu Riot ID (`Nome#TAG`).
2. **Gravação**: arraste o .zip do Craig (ou cole o caminho, que é mais rápido para arquivos grandes).
3. **Partida**: clique em *Buscar minhas partidas*. A que bate com o horário da gravação já vem marcada.
4. **Sincronização**: deixe a opção padrão se você falou "espumas" na barreira do round 1.
5. **Jogadores**: confira quem é quem no Valorant. Fica salvo para as próximas.
6. **Analisar**. O progresso aparece à direita; ao terminar, clique na análise para ver o relatório.

## Gravando a partida

1. Adicione o [Craig](https://craig.chat) ao servidor do Discord.
2. Todos na call de voz → `/join` antes da partida.
3. **Quando a barreira cair no round 1, fale "espumas".**
4. No fim, `/stop`. No link que o Craig mandar, baixe em **Multi-track → FLAC**.

> Use o voice do Discord, não o do Valorant — só o Discord separa as faixas.
> Avise o time que a call está sendo gravada; o Craig também anuncia isso.

### Como a sincronização funciona

- Vale **só uma** ocorrência da palavra, **perto do começo**. Com o horário da gravação (o Craig salva) e o da partida, o programa sabe mais ou menos onde o round 1 está e só aceita a palavra até 4 min antes ou depois dali. Sem horário, só nos primeiros 15 min. Toda repetição depois é ignorada e aparece listada no relatório.
- Se houver mais de um "espumas" nessa janela (ex.: "bora espumas" no lobby), fica o mais próximo de onde o round 1 deveria estar. Se as mortes apontarem claramente outro, fica o das mortes.
- **Ajuste fino**: quem morre quase sempre fala logo depois. O programa testa pequenos deslocamentos e só aplica um ajuste quando as mortes concordam com folga. O resultado aparece no relatório.
- Esqueceu de falar? Escolha *Não falei*: usa o horário do Craig x API mais o ajuste pelas mortes. Ou informe em que ponto da gravação a barreira caiu.
- Falou em outro momento? Escolha *em outro momento* e diga o round, a fase e o que o relógio mostrava.

## Linha de comando

```powershell
python -m espumas web                                   # interface
python -m espumas analisar craig.zip -n "Ascent 13-11"  # só a call
python -m espumas analisar craig.zip --partida ultima   # com a última partida (precisa do config)
python -m espumas relatorio saida\<pasta>\analise.json  # refaz métricas sem transcrever
python exemplos\demo.py                                 # relatório de exemplo, sem nada instalado de GPU
```

Cada análise fica em `saida\<pasta>\`: `relatorio.html`, `transcricao.txt`, `transcricao.srt` (legenda para a gravação do OBS), `analise.json` e `cache\` (rodar de novo não retranscreve).

### Tempo e recursos

Com a RTX 5070 o `large-v3-turbo` transcreve muito mais rápido que o tempo real; uma partida de ~40 min × 5 faixas deve levar poucos minutos (o VAD pula os silêncios). Usa só alguns GB dos 12 GB de VRAM.

## Configuração

A interface grava tudo em `config.yaml`. Dá para editar à mão; veja `config.example.yaml` com todas as opções (limites das métricas, janelas da sincronização, vocabulário e correções).

O Whisper erra jargão. Já vem um glossário de Valorant embutido e correções comuns (`jet` → `Jett`, `espaique` → `spike`, `kill joy` → `Killjoy`...). Para o resto:

```yaml
vocabulario:        # palavras que o modelo deve "conhecer"
  - Kaio
correcoes:          # erros que se repetem na sua call
  "caio": "Kaio"
```

## Problemas comuns

| Erro | Solução |
|---|---|
| `CUBLAS_STATUS_NOT_SUPPORTED` | CTranslate2 antigo sem suporte à série 50: `pip install -U "ctranslate2>=4.5.0" faster-whisper` |
| `Could not load library cudnn_ops64_9.dll` / `cublas64_12.dll` | `pip install -U nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"` dentro do `.venv` |
| `Nenhuma GPU CUDA encontrada` | Atualize o driver NVIDIA e reinicie |
| Falta de VRAM | No config: `compute_type: int8_float16` |
| "Chave da HenrikDev API recusada" | Confira a chave em Configurações |
| Palavra de sinc não encontrada | Veja na transcrição como o Whisper escreveu e ajuste a palavra, ou use *Sei em que ponto da gravação* |
| Rounds deslocados no relatório | Veja o quadro **Sincronização**: se as mortes sugerem um deslocamento, ajuste `sinc.buy_fase_s` ou use outra opção de sinc |
| Texto inventado em silêncio | Já é filtrado; se aparecer outra frase recorrente, adicione em `ALUCINACOES` em `espumas/transcribe.py` |

## Limitações

- As métricas são automáticas: **ponto de partida para revisar a call**, não veredito. Uma interrupção pode ser um callout urgente e correto; fala de morto pode ser info útil.
- A HenrikDev API é não oficial: pode mudar ou ficar fora do ar.
- O fim de cada round é estimado (última kill, defuse ou spike explodindo).
- Ainda não foi validado com uma partida real: a primeira análise serve de calibração.

## Próximos passos

- [ ] **Tom de voz**: emoção pelo áudio (emotion2vec) + leitura do texto por um LLM local (tilt, crítica, irritação).
- [ ] Classificar cada fala: callout, estratégia, conversa paralela, reclamação.
- [ ] Comparar partidas (evolução do time ao longo do tempo).

## Desenvolvimento

```powershell
pip install -r requirements-dev.txt
pytest
```

Os testes não precisam de GPU nem de chave: usam áudio sintético, uma partida falsa no formato da API e uma transcrição falsa.
