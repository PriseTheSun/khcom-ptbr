# Consumidores das fontes de créditos

A busca da árvore completa fixada encontrou **um produtor textual externo**,
`StaffRollRunCredits`, e **um dono das tabelas de fonte**, `sroll_tmr.c`.
A revisão dos campos, tabelas de funções e dados da ROM não identificou outro
consumidor dos atlas de créditos. Isso sustenta um piloto privado de reuso dos
índices 210–233 na revisão US, acompanhado das provas dinâmicas; não transforma
esses glifos existentes em espaço livre universal nem fecha QA do jogo inteiro.

Esta investigação é somente leitura. Não alterou ROM, renderer, atlas ou save.
Ela amplia a cobertura fonte de [credits-reference-investigation.md](credits-reference-investigation.md),
que examinou 12 arquivos C/header; não substitui suas âncoras Thumb nem o ensaio
dinâmico independente das variantes Sora/Riku.

## Cobertura e aquisição

Foi usada a árvore Git primária do commit
[`5dc49b75068bfe24e07bdaf365570d64682680c3`](https://github.com/Pheenoh/khcom/tree/5dc49b75068bfe24e07bdaf365570d64682680c3),
com `truncated=false`, retida em
`private/reports/credits-consumers-v1/upstream-tree.json`. Foram examinados todos
os **750 arquivos** sob `src/`, `include/` e `asm/`: 269 C, 274 headers,
200 includes e sete assembly, somando **11.706.386 bytes**. Os 64 manifestos
de assets e 12 de texto já fixados também foram pesquisados por donos das fontes
e tabelas de despacho. Não foi compilado ou executado código upstream.

Cada arquivo adquirido foi comparado ao Git blob SHA-1 da árvore e ganhou
SHA-256/tamanho na evidência privada. `tools/khcom/upstream.py:read_source`
é usado novamente para conferir esses bytes durante a auditoria; não há outro
parser de fontes do projeto ou downloader permanente. O archive oficial e os
hashes permanecem privados. A leitura não se limita aos arquivos que retornaram
resultados na busca.

O manifesto público foi **restaurado byte a byte aos 107 arquivos anteriores**.
O corpus completo permanece em `.deps/khcom` e no manifesto privado
`private/reports/credits-consumers-v1/corpus-manifest.json`. Isso evita impor
837 downloads seriais ao primeiro uso das ferramentas de edição ou à CI.
Os 17.905 bytes do manifesto público e os 135.032 bytes do privado cabem no
limite de 256 KiB do leitor. Cinco verificações locais com cache aquecido
mediram 6,2–8,2 ms para 107 arquivos e 27,1–30,6 ms para 837; o tempo de CPU
foi próximo ao tempo decorrido. O pico do único processo Python foi 27.164.672
bytes, compartilhado pelas duas medições. Não houve benchmark de disco frio
ou de aquisição serial via HTTP. A aquisição única do archive foi observada
em 0,487 s; seu preparo/verificação levou 0,141 s. Não foram medidos CPU/memória
da aquisição, nem consumo de tokens da investigação.

`acquisition.json`, `acquisition-performance.json`, `report.json` e `audit.py`,
sob `private/reports/credits-consumers-v1/`, preservam cobertura, consultas,
linhas, hashes e limitações. A auditoria final revalida os 750 Git blob hashes
e os SHA-256. Fontes adicionais de pesquisa não integram a distribuição.

## Fluxo de dados examinado

As 146 linhas que mencionam `SrollText*` estão em dois headers e dois C:
`sroll.h`, `sroll_api.h`, `mode_staffroll.c` e `sroll_tmr.c`. Isso inclui
declarações/definições, não 146 chamadas. Além dessa busca lexical, foram
seguidos os contratos abaixo.

| Dono ou fronteira | Resultado da revisão |
|---|---|
| `SrollWork` e `StaffRollWork.text` | O contexto textual é um membro do estado privado do modo. `sStaffRollWork` é estático em `mode_staffroll.c`; os usos de `&work->text` permanecem nas chamadas textuais desse produtor. Não apareceu escape do contexto para outro módulo na fonte examinada. |
| `SrollTextSelectFont` | Limita o seletor a 0/1 e copia páginas, bitmaps, larguras e contagem de `gStaffRollFonts` para o contexto. É o único escritor nominal desses campos fora da inicialização comum. |
| `SrollTextMeasureWidth` / `EnqueueString` | Ambos derivam códigos da string: pares quando o primeiro byte tem bit 7; mapa de byte simples nos demais casos. O produtor fornece apenas as linhas do array US ou buffers derivados delas, além de espaço/til usados na medição. |
| `SrollTextProcessNextChar` | Obtém código da fila e calcula endereço e largura a partir do mesmo contexto. Comandos internos podem selecionar fonte, mas não fornecem outro ponteiro de atlas. |
| `DrawStringAtPixelX` | Acrescenta apenas o glifo `0x8140`, índice 0, para preenchimento lateral. Esse índice deve permanecer preservado. |
| `gStaffRollBlit1bppFuncs` / `2bppFuncs` | São chamadas indiretas reais, indexadas por **largura**, com nove entradas para 0–8. Recebem o ponteiro de pixels já calculado; não escolhem outro atlas nem outro índice de caractere. Todos os alvos nominais `SrollBlit*Width*` estão no mesmo C. |

As referências fonte estão em
[`mode_staffroll.c`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/src/sroll/mode_staffroll.c#L3468),
[`sroll_tmr.c`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/src/sroll/sroll_tmr.c#L537),
[`sroll.h`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/include/sroll/sroll.h#L147)
e no manifesto
[`staff_roll_font.yaml`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/config/assets/staff_roll_font.yaml#L325).
As ocorrências de `glyphHeight` em `msg.c` pertencem a outro tipo e outros
bancos de fonte; a igualdade do nome do campo não estabelece compartilhamento.

Não foi encontrado uso de endereço de função `SrollText*` fora da forma
lexical seguida por `(`. Essa verificação inclui declarações e chamadas;
não é uma análise formal de pontos de destino. As funções indiretas do blitter
foram encontradas porque também se examinaram tipos, campos e manifestos,
sem limitar a investigação aos nomes da API textual.

Nomes/cargos animados, cabeçalhos e logos dos créditos usam outra rota:
`sroll_a_name.c`, `sroll_b_secn.c` e `sroll_b_logo.c` carregam tiles, frames,
animações e paletas próprios por `LoadObjTiles`/`AnimInit`. Eles não recebem
`SrollWork` ou os bitmaps de `gStaffRollFonts`. Os comandos de roteiro `*`,
`<` e `[` criam essas tarefas gráficas; continuam exigindo localização de
texto em imagens. Ícones e fontes de mensagens/menus também têm proprietários
distintos. Um mesmo número de glifo em outro atlas não autoriza alterá-lo.

## Verificação adicional nos bytes da ROM

A busca examinou as **8.388.608 posições u32 alinhadas** da ROM de 32 MiB,
aceitando valores tanto no início quanto no interior dos oito recursos de
fonte. Encontrou 16 palavras candidatas:

- Oito correspondem às referências já estabelecidas: dois literais de código
  e seis campos dos dois registros `SrollFont`.
- Três palavras estão dentro de payloads de tiles 4bpp de dois sprites de
  Riku. Seus limites foram conferidos com a extração/reinserção exata já
  existente; ficam fora dos registros de frames/animações.
- Três estão no filme de abertura: duas no payload de vídeo e uma no de áudio,
  fora do cabeçalho/tabelas de tamanhos, seguindo o envelope de `MovieOpen`.
- Duas estão no payload de blocos de áudio dos créditos, fora dos cabeçalhos,
  seguindo `ReadNextAudioBlock`. O decoder consome bits/amostras.

As oito coincidências em payloads não são evidência de ponteiros de fonte.
Seus donos, intervalos, hashes e classificação foram preservados no relatório.
Nenhum valor aponta diretamente para os intervalos dos índices 210–233.
Não foi feita auditoria exaustiva dos codecs de filme. A busca alinhada não
exclui constantes desalinhadas, endereços calculados, aliases de memória ou
referências codificadas; não deve ser apresentada como grafo completo da ROM.

## Decisão delimitada sobre 210–233

Para o decoder de strings, os 24 índices correspondem exatamente aos códigos
`82A0`–`82B7`. Nenhum byte simples de 0 a 127 no mapa original os produz.
São desenhos japoneses existentes, **não células vazias**. Eles não aparecem
no ledger do roteiro US; a prova dinâmica original das duas variantes deve
ser lida juntamente com esta análise estática, preservando sua cobertura real.

Um piloto US pode substituir somente estas quatro regiões, mantendo tamanho
e endereços dos arrays:

| Recurso | Intervalo exclusivo de fim | Bytes |
|---|---|---:|
| Bitmap fonte 0 | `[0x09A56740,0x09A56A40)` | 768 |
| Bitmap fonte 1 | `[0x09A59BA0,0x09A59D20)` | 384 |
| Larguras fonte 0 | `[0x09A545D2,0x09A545EA)` | 24 |
| Larguras fonte 1 | `[0x09A547DE,0x09A547F6)` | 24 |

Isso não exige editar ícones, outro atlas, ponteiros, páginas ou código do
renderer. O codec PT-BR deve tornar explícita a interpretação dos códigos
reutilizados e preservar o round-trip do original em seu perfil original.
As novas larguras devem respeitar os blitters de 0–8 e os limites de linha;
preservar bytes fora dessas regiões é uma condição verificável da candidata.

A recomendação é **avançar para esse piloto privado**, com prova visual dos
24 desenhos nos dois estilos e comparação do roteiro original antes/depois.
Não há consumidor fonte pendente identificado que exija modificar ícones.
Permanecem limites reais: não foi produzido build matching completo, uma
prova formal de ausência de referências calculadas ou QA de toda a campanha.
O reuso é específico da revisão USA e do conjunto de entradas demonstrado;
não se estende às ROMs JP/EU ou a texto arbitrário fornecido posteriormente.
Nenhuma tarefa geral M2.5–M2.9 ou de cobertura integral foi marcada aqui.
