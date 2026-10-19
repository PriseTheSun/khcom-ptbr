# Extração gráfica sem perda

```sh
.venv/bin/python tools/extract_graphics.py --rom private/rom/B8CE.gba \
  --scope known --out private/graphics/extracao-nova
```

`--scope fonts` (padrão) mantém a inspeção específica das cinco fontes.
`--scope known` seleciona os recursos gráficos dos 64 manifestos fixados,
verifica a ocupação contra a ROM identificada e publica somente em uma pasta
privada nova. A ROM e saídas anteriores nunca são sobrescritas.

Cada recurso contém `original.bin`, representações editáveis e `resource.json`
com spans, digests, nome de entrada, papel e resultado da reconstrução.
Um `report.json` na raiz só é gravado após a conclusão de todos os recursos.
Falhas preservam a pasta parcial e retornam erro; ela não é uma extração completa.

## Preservação por formato

| Recurso | Representação e prova |
|---|---|
| Sprite sheets | PNG principal e pilha de camadas extras, layout, OAM e animações; parser fixado reconstrói os registros e tiles, incluindo flips e tiles compartilhados |
| Tiles 4/8 bpp | PNG indexado; reconstrução da ordem de tiles/nibbles e comparação integral |
| Fontes compactas | PNG indexado e geometria; recodificação do bitmap original |
| Paletas | Todas as palavras u16, inclusive bit alto, e prévia RGB separada; RGB não substitui os bytes originais |
| Tilemaps | Palavras u16 completas preservam todos os bits; modo de tela, dimensões e composição ficam desconhecidos até verificar o consumidor |
| Compressão não implementada | Bloco original retido, com `roundtrip_equal=false`; nunca conta como decode verificado |

O vínculo `palette` do manifesto pode apontar a armazenamento `raw`, como
`gSramErrorPalette`. O relatório conserva `format=raw` e registra o papel
`interpreted_as=palette`. Outros blocos brutos não recebem esse papel por nome
ou heurística. As prévias usam a paleta indicada, quando existe, e níveis de
cinza para índices ausentes. Não são prova das cores/transparência em runtime;
os índices originais e as palavras da paleta permanecem preservados.

## Verificação executada

`private/graphics/known-v3/report.json` registra **4.900 reconstruções exatas**:
1.942 sprite sheets, 703 atlas de tiles (701 de 4 bpp e dois de 8 bpp),
1.173 tilemaps, 1.079 paletas e uma paleta armazenada como `raw`, além de duas
fontes de créditos. Nenhum recurso selecionado declara compressão nessa revisão.
V3 também conserva o caminho do ZIP e o membro explicitamente selecionados.
O conjunto foi extraído sem executar o build/extrator upstream ou `gbagfx`.

Os testes públicos usam pixels autorais: ordem 2D de tiles, nibbles, índices
acima de 127, paletas com bit alto, flips, animação e tiles emprestados, falhas
de geometria/limites e bloco comprimido não interpretado. O relatório real da
ROM é evidência distinta desses testes.

A extração v1 falhou ao encontrar a paleta `raw` e foi preservada como pasta
parcial. V2 cobre esse caso no produtor e passou. V3 corrige os nomes dos PNGs e descreve o empilhamento: `main.png` contém a
camada 0; `extra-layers.png` empilha verticalmente as camadas seguintes.
`layer_count` e `png_layers` preservam quantidade, ordem e altura de cada
camada. Há 146 recursos com 3–6 camadas; a segunda imagem não é uma camada única.

O custo de V3, medido por
`/usr/bin/time -l`, foi 22,45 s de parede, 16,13 s de CPU usuário e 5,94 s de
CPU sistema, com RSS máximo de 239.992.832 bytes. Uma execução, um processo,
fontes/caches existentes; sem comparação controlada cold/warm ou custo de tokens.
Logs: `private/reports/graphics-known-v3.log` e `.time.txt`.

## Cobertura ainda aberta

O sucesso fecha a extração/reconstrução dos recursos gráficos descritos,
não o inventário de toda a ROM. Regiões desconhecidas, vídeos, identificação
de texto nas imagens e composição por tela ainda exigem investigação.
Também faltam edição/recompressão com crescimento, realocação comprovada e
revisão dos consumidores após alterações. Todos os arquivos aqui extraídos
permanecem privados e excluídos do staging público.
