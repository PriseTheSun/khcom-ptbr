# Filmes, legendas e título raster

O inventário US cobre cinco filmes, 3.605 quadros, 29 registros declarados de
legenda e 27 registros selecionados pelo modo de vídeo. Dois registros são
placeholders vazios de tabelas que o modo US não seleciona. Há 28 itens únicos
no catálogo de legendas. Esta prova fecha a investigação e reconstrução de um
segmento audiovisual; não declara traduzidas as 24 linhas ativas restantes nem
concluídas as campanhas.

## Identidade e reprodução

ROM US SHA-256:
`6f6e7b61bb7b6ef7e2bea6e9dd01e70570a715835cc3713abe86186fd2c4e28d`.
O [baseline matching](matching.md) recompilado é idêntico à ROM integral.
O contrato [movie-codec-v1.json](../manifests/movie-codec-v1.json) registra commit,
hashes das fontes e resultados; não contém pixels nem áudio do jogo.

```sh
.venv/bin/python tools/audit_movies.py --rom private/rom/B8CE.gba \
  --out private/meu-inventario-de-filmes.json
.venv/bin/python tools/probe_movie.py --rom private/rom/B8CE.gba \
  --kind opening-subtitles --out private/minha-abertura-legendas.gba
.venv/bin/python tools/probe_movie.py --rom private/rom/B8CE.gba \
  --kind opening-title --out private/minha-abertura-titulo.gba
```

As CLIs também aceitam ZIP com `--member`. Cada receita recebe a ROM original
e gera um candidato independente. A composição deve combinar diferenças contra
a mesma origem e rejeitar conflitos, em vez de alimentar uma ROM já alterada a
um produtor cujo perfil exige a original.

As capturas privadas executam o modo real de vídeo em mGBA 0.10.5, depois da
inicialização normal da tela de título. Três escritas RAM diagnósticas selecionam
campanha, argumento e modo pendente. Elas ficam registradas; não representam uma
rota jogada até o final. Cada quadro é capturado após a decodificação pelo ARM
original, e cada frame do core conserva estado da legenda. ROM, saves e entrada
original não são modificados; o relatório verifica a ROM também na memória do
core. O programa termina ao sair do modo de vídeo.

| Recurso | Quadros a 15 fps | Áudio mono | Imagens de display únicas |
|---|---:|---:|---:|
| Abertura | 1.617 | 31.536 Hz | 1.760 |
| Evento 026 | 48 | 13.379 Hz | 58 |
| Evento 057 | 257 | 13.379 Hz | 288 |
| Final Sora | 894 | 26.758 Hz | 1.023 |
| Final Riku | 789 | 26.758 Hz | 905 |

Foram conservados todos os 3.605 quadros brutos, 4.034 imagens distintas do
display, tabelas completas por frame, 14 folhas de contato cobrindo todos os
quadros e resultados OCR por quadro, em `private/movies-v1/`. Todas as folhas
foram examinadas; candidatos OCR e o logo também receberam inspeção ampliada.
OCR é triagem: seus falsos positivos em roupa, sombras, argolas de caderno e
textura não viram itens de tradução automaticamente.

Texto raster observado: marcas Disney, Square Enix e Kingdom Hearts, e o
subtítulo do jogo no logo da abertura. A decisão explícita do usuário foi
preservar as marcas/Kingdom Hearts e traduzir o subtítulo para **Corrente de
Memórias**. Não foi observado outro texto raster nos quatro filmes restantes.
As legendas sobrepostas são inventariadas separadamente, incluindo linhas de
finais e nomes próprios. Isso não cobre a tela de título tiled, os créditos ou
imagens de outros modos; cada recurso precisa de sua própria ocorrência.

## Framing e codecs

`khcom.movies` é o único parser do container: valida dimensões, taxa, tipos,
contagens, spans, alinhamento e soma de comprimentos dos pacotes. Conserva as
caudas opacas como ocupadas; elas nunca autorizam espaço livre. As tabelas de
legendas são confrontadas com os registros ABI de 16 bytes na ROM e com a fonte
US fixada, em vez de inferir sua seleção pela simples existência de símbolos.

`khcom.movie_delta` é o dono da representação de vídeo. A interpretação vem de
`asm/movie_codec.s` e `src/lib/movie_player.c` do baseline matching, sem atribuir
ao stream um nome comercial de codec por semelhança:

- Keyframes: dois endpoints RGB555 e 16 seletores de dois bits por bloco
  16×16; interpolação horizontal/vertical em dois passes.
- Delta: cabeçalho com tamanhos dos streams de bits/cores, seguido de vetores;
  bits MSB-first dentro de palavras little-endian. Blocos 8×8 são subdivididos
  horizontal/verticalmente até pares de pixels. Operações: copy, motion, adição
  de cor, fill e literal.
- O vetor de oito bits seleciona deslocamento de −8 a +7 em cada eixo.
  A adição segue as palavras ARM de 32 bits, inclusive carry entre dois pixels.
  A interpolação vertical também preserva o efeito do deslocamento da palavra
  completa no bit 15, embora esse bit não apareça no RGB exibido.
- Tipo 2 aplica o filtro de fronteira depois do delta. O encoder conserva o
  tipo de cada quadro; não remove o filtro para tentar simplificar a prova.

O parser/encoder reproduziu **byte a byte os 3.590 pacotes delta originais**.
O decoder independente reproduziu o RGB de **todos os 3.605 quadros**, incluindo
15 keyframes e 48 quadros com postprocessamento, contra capturas do jogo. Nos
137 últimos quadros da abertura, a comparação adicional é exata em todos os
16 bits por pixel, não apenas nos 15 visíveis. Os 3.605 quadros foram verificados
em 36,55 s em processo frio com arquivos já em cache; não se mediu pico da
família de processos ou tokens desse experimento.

## Piloto das três legendas de abertura

`khcom.movies.build_opening_subtitle_probe(original)` altera três payloads em
suas reservas originais, sem mover ponteiros, registros, tipos ou timing.
Os limites usados são 62/64/56 bytes; as traduções ocupam 62/52/54 bytes.
Caudas não utilizadas permanecem idênticas à ROM original. A fonte latina
existente fornece os acentos. Larguras de avanço 159/136/69 px e limites de tinta
41–200, 52–188 e 86–155 cabem na tela; o consumidor ignora espaços iniciais e
acumula espaços internos no avanço do glifo anterior.

Alvo SHA-256:
`3526ea8628191732eb849d787e5ffdf72c23fe20804be5c59d08c29b29285032`.
O replay produziu 1.617 quadros brutos idênticos e 6.454 registros do display.
Seleção/lifetime das legendas permanecem iguais. Seis entregas do decoder
mudam até um frame do core; existem diferenças de varredura/tearing fora da
legenda. Portanto, não se afirma identidade integral dos screenshots nem de
cada instante de execução. O início/fim do filme e seus registros de duração
permanecem iguais. As capturas `core-3717.png` e `core-4314.png` comprovam
primeira linha e duas linhas finais, com acentos e sem corte.

Evidências privadas: `opening-ptbr.json`,
`opening-ptbr-runtime/{report.json,display.jsonl,video.jsonl}`,
`opening-subtitle-runtime-proof.json` e `opening-ptbr-independent.json`.
O BPS histórico desse piloto tem 225 bytes e foi aplicado pelo codec do projeto
e por Flips, produzindo o mesmo alvo. A mudança posterior do gerador BPS não
altera essa evidência histórica nem o SHA da ROM de destino.

## Piloto do subtítulo raster da abertura

`khcom.movie_title.build_opening_title_probe(original)` deriva fontes e vídeo
exclusivamente da ROM fornecida. Renderiza **CORRENTE DE MEMÓRIAS** numa placa
azul/dourada de 144×16 px, na posição do subtítulo anterior. A largura do texto
é 110 px. Há fade de entrada/saída; o keyframe de encerramento conserva sua
paleta e quantiza apenas os seletores atingidos, acompanhando o desfoque
original. Esse quadro transitório é deliberadamente lossy, como o original.

Os quadros 1.520–1.610 são editados. O retângulo básico é `[48,72,192,88)`;
interpolação/filtro ampliam a pegada total a `[45,69,193,89)`. Não há letras
inglesas residuais no antigo subtítulo. O logo Kingdom Hearts e as marcas
permanecem visíveis. A placa é uma solução gráfica de piloto, sujeita à revisão
estética do usuário, sem ser apresentada como a arte tipográfica original.

Para caber no recurso, a compactação sem perdas funde subárvores idênticas de
copy/motion/fill. Ela **não** funde adições entre colunas, pois isso alteraria o
carry ARM. Isso economiza 33.900 bytes do stream original. A receita inteira
usa 12.780 bytes menos que a capacidade existente, preenchidos depois dos
streams consumidos em pacotes delta pertencentes ao próprio filme. Não usa
caudas opacas, padding ROM presumido, RAM adicional ou realocação para outro
recurso. Maior quadro editado: 5.464 bytes; reserva de decode: 8.192 bytes.

Alvo SHA-256:
`5f10e20c2699009ca0cd90ce9721b03b403f94a308feff840ad4dd618238ca33`.
Replay independente: **91 quadros editados exatos em RGB555 u16**, outros
**1.526 quadros RGB idênticos**. Início no frame do core 953, saída no 7.407,
iguais ao baseline. Quatorze entregas variam até um frame do core. Áudio,
tabelas de legenda, tipos de quadro, fps, outros filmes e tamanho de 32 MiB
permanecem iguais. Essa separação entre frames lógicos e varredura do display
evita esconder jitter de execução atrás de um hash de arquivo.

Evidências privadas: `title-ptbr.json`, `title-pixel-footprint.json`,
`title-ptbr-runtime/`, `title-runtime-proof.json` e previews 1.520, 1.525,
1.530, 1.590, 1.607, 1.608, 1.609 e 1.610. O CLI público reproduziu o SHA em
26,05 s de parede, 26,01 s de CPU, RSS máximo de 191.299.584 bytes, processo
frio/cache de arquivos quente. Pico da família de processos, cold filesystem
e tokens não foram medidos.

## BPS de recursos recomprimidos

`khcom-linear-coalesced-v2` une pequenos trechos coincidentes entre diferenças
em um TargetRead, preservando runs de oito ou mais bytes como SourceRead.
O produtor anterior excedia 65.536 registros de literais no vídeo; apenas
ampliar o limite teria mantido a fragmentação do relatório. O produtor novo
mantém os limites de ações/literais e inclui, em cada literal,
`coalesced_source_ranges: [{source_start, length, source_sha256}]`.
Esses intervalos correspondem aos mesmos offsets no destino e registram todos
os bytes de origem incorporados. A soma de registros de proveniência também
obedece ao orçamento existente `MAX_ACTIONS`.

Nenhuma dessas faixas concede permissão de distribuição. Um literal que contém
bytes coalescidos da origem precisa de classificação conservadora como derivado
da ROM local, mesmo se os demais bytes forem texto português. O patch desta
reconstrução continua privado, pois contém recursos derivados da ROM.

O BPS v2 do título tem 2.246.395 bytes, 1.734 literais e 65.865 intervalos de
origem, totalizando 79.197 bytes coalescidos. Aplicadores do projeto e Flips
produzem o mesmo alvo. Um BPS gerado independentemente por Flips tem 728.482
bytes e também é aceito por ambos os aplicadores. Onze testes BPS, incluindo
interoperabilidade real com Flips, e nove testes de framing/codec passaram.
O fluxo create/apply/Flips/JSON v2 levou 0,603 s de parede e 0,354 s CPU Python,
RSS Python 287.588.352 bytes. O gerador anterior falhava; não há comparação
antes/depois de dois trabalhos concluídos. Pico agregado e tokens não medidos.

## Limites de cobertura

Esta entrega prova reconstrução audiovisual no jogo real e identifica os
consumidores de legendas. A revisão editorial das 24 outras linhas ativas,
checagem audiovisual após combiná-las, tela de título tiled e restante do jogo
continuam gates próprios. Vozes e música originais são preservadas; este trabalho
não implementa dublagem. Capturas e vídeos derivados são exclusivamente privados.
