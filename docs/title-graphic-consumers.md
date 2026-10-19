# Reinserção do prompt gráfico e consumidores compartilhados

O piloto `khcom.graphic_probe.build_title_probe` substitui **PRESS START** por
**APERTE INICIAR** nos cinco quadros da animação do título. A ROM candidata tem
SHA-256 `562c09cde6de9e098c0544ab9fcbc091a5abbfbfd08283f34e4e452ec6e6d113`;
a origem é a USA B8CE rev0 documentada em [matching.md](matching.md). Somente
298 bytes mudam, todos dentro do recurso do prompt. O logo e outros textos
são recursos separados e continuam pendentes.

A reinserção usa os índices reais de tiles nos registros OAM, mantém paleta,
animações e alocação, exige bytes idênticos em todos os usos de um tile
compartilhado e redecodifica todas as camadas para comparar os pixels pedidos.
Uma edição conflitante falha com `graphic_shared_conflict`. Isso não depende
de o empacotador/deduplicador upstream produzir uma imagem editada do mesmo
tamanho; a geometria original é uma restrição explícita da operação.

## Limites do recurso e referências

O nome `gTitlePressStartTiles` do manifesto engloba os registros e os tiles,
no intervalo `[24581436,24583526)`, com 2.090 bytes. O símbolo homônimo do ELF
aponta somente para o payload: `[24581734,24583526)`, com **1.792 bytes / 56
tiles 4bpp**. Os primeiros 298 bytes são registros, preservados integralmente.
Misturar as duas fronteiras daria uma conclusão incorreta sobre os consumidores.

A auditoria fresca do baseline matching verifica os 524 objetos e todas as
relocações antes de selecionar as referências do prompt:

| Consumidor | Offset da referência | Destino na ROM |
|---|---:|---:|
| `title.o`, carga de tiles | 878204 | 24581734 |
| Tabela de quadros, quadro 0 | 32466416 | 24581436 |
| Tabela de quadros, quadro 1 | 32466420 | 24581488 |
| Tabela de quadros, quadro 2 | 32466424 | 24581540 |
| Tabela de quadros, quadro 3 | 32466428 | 24581592 |
| Tabela de quadros, quadro 4 | 32466432 | 24581644 |
| Tabela de animações | 32466436 | 24581696 |

As tabelas são referenciadas por `title.o` nos offsets 878216 e 878220.
A busca de palavras de 32 bits cobre **todos os alinhamentos da ROM** e todos
os destinos interiores do recurso. Além das sete referências, aparecem seis
coincidências, verificadas pelo produtor `khcom.matching_assets`:

| Offset com aparência de ponteiro | Dono real | Formato |
|---|---|---|
| 1681688 | `gMovieOpening` | pacote de vídeo |
| 8293163 | `gMovieRikuEnding` | pacote de vídeo |
| 9362810 | `gSor1ll56Tiles` | tiles 4bpp |
| 28518071 | `gBlockAudioData` | payload de bloco de áudio |
| 30407058 | `gStaffRollRikuScene13Tiles` | tiles 4bpp |
| 30852192 | `gStaffRollRikuImage1Palette` | cores u16 |

Esses seis valores pertencem a dados codificados, com arquivos, manifestos,
limites e identidade com a ROM verificados; não são ponteiros a atualizar.
Os dois pacotes de vídeo também passam pelo parser do codec e pelas fontes
do decoder já vinculadas ao matching. Não resta candidato não explicado
nessa busca. Endereços calculados arbitrariamente em ARM continuam fora do
alcance de uma busca de palavras; a fonte completa do consumidor e a execução
real abaixo completam a evidência delimitada deste prompt.

Os 64 manifestos examinados contêm 11.347 entradas USA e nenhuma declara
compressão. Isso não prova ausência de formatos comprimidos opacos no jogo.
Para **este recurso**, a fonte matching chama `LoadObjTiles` com 1.792 bytes;
o dono encaminha o payload diretamente a `RequestDma3Copy`. A verificação da
VRAM confirma a mesma identidade. Portanto, não há recompressão aplicável a
este payload 4bpp. A reconstrução do codec de filmes é uma prova separada em
[movies.md](movies.md), sem ser tratada como compressão de tiles.

## Execução real e composição

O diagnóstico privado executa mGBA 0.10.5 desde reset, sem entradas e **sem
escritas diagnósticas em RAM**, até terminar a entrada do título. Entre os
core frames 1400 e 1500, intercepta a entrada de `DrawSprite` para os cinco
endereços de quadro e verifica em cada chamada:

- o objeto de tiles aponta para o payload esperado e contém 56 tiles;
- todos os 1.792 bytes de OBJ VRAM são iguais aos tiles da respectiva ROM;
- a sequência dos 100 draws, ponteiros e quadros é idêntica entre original e
  candidato, com contagens `[12,28,24,24,12]`;
- os cinco quadros aparecem completos em captura e mantêm botão, barra,
  paleta e composição. As diferenças ficam no retângulo `[24,144,115,152)`
  da tela, que abrange a troca das letras.

As cinco comparações foram inspecionadas visualmente. O título permanece
estável, com **APERTE INICIAR** legível em cada quadro. Esse teste comprova o
prompt na tela de título, não progressão das campanhas nem localização total.
A primeira captura exploratória pegou a entrada da tela com texto ainda fora
do campo; ela foi preservada e não é usada como prova da composição final.

A evidência privada é `private/title-consumers-v1/consumer-proof.json`,
`visual-proof.json`, `original-stable/`, `translated-stable/` e
`stable-comparison.png`. O resumo mantém os consumidores de cada tile,
referências e hashes dos artefatos; `summarize.py` o reproduz a partir dos
fatos canônicos e das capturas. A auditoria matching completa está em
`private/matching-v1/title-consumer-facts.json`. Relatórios registrados são
evidência histórica, não uma autorização editável para alterar outros recursos.
ROM, tiles, capturas e patches derivados permanecem privados.
