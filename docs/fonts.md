# Fontes: prova de bytes e piloto de diálogo

O extrator selecionado verifica cinco recursos de fonte contra a ROM USA,
gera PNGs privados e reencoda cada PNG para demonstrar igualdade dos bytes.
São 1.379 glifos, sem alegar inventário completo de gráficos, paletas reais
ou funcionamento de todos os renderers. Os formatos continuam sob propriedade
dos parsers fixados do projeto khcom; não existe um segundo decodificador
manual de tiles ou PNG.

```sh
.venv/bin/python tools/extract_graphics.py \
  --rom private/rom/B8CE.gba --out private/fonts/us
```

A saída deve ser uma pasta nova dentro de `private/`. O relatório preserva
endereços, hashes de payload/PNG/glifo, dimensões, bounds de pixels não nulos,
contagem de glifos, métricas e suas limitações. `--fetch-upstream` obtém somente
fontes oficiais ausentes, verificadas pelo manifesto/hash fixados. A ferramenta
não baixa ROMs e não modifica gráficos ou ROM.

| Recurso | Glifos | Formato | Prova local |
|---|---:|---|---|
| `gMsgLatinFontTiles` | 256 | sprites 4bpp, células 16×16 | PNG reversível e tabela de ponteiros de frames conferida |
| `gSmallFontTiles` | 45 | sprites 4bpp, células 8×8 | PNG reversível e tabela de ponteiros conferida |
| `gBgTextSmallFontTiles` | 30 | sprites 4bpp, células 16×16 | PNG reversível e tabela de ponteiros conferida |
| `gStaffRollFont0Glyphs` | 524 | glifos lineares 2bpp, 8×16 | PNG reversível e 524 larguras conferidas |
| `gStaffRollFont1Glyphs` | 524 | glifos lineares 2bpp, 8×8 | PNG reversível e 524 larguras conferidas |

Os assets e seus offsets vêm de
[`sprites_msg.yaml`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/config/assets/sprites_msg.yaml)
e [`staff_roll_font.yaml`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/config/assets/staff_roll_font.yaml).
O processamento usa somente as funções revisadas de
[`assetgen.py`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/tools/assetgen.py)
e [`sprite_sheet.py`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/tools/sprite_sheet.py),
carregadas de bytes verificados. Nenhum build, subprocesso, extrator completo
ou comando de upstream é executado por esta ferramenta.

## O que já existe na fonte latina

A estrutura `GlyphWidthTable` declara `u16 widths[256]` em
[`msg_types.h`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/include/evt/msg_types.h).
O literal `sLatinGlyphWidths` de
[`msg.c`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/src/msg/msg.c)
foi selecionado para US, serializado em u16 little-endian e correspondeu
exatamente a uma ocorrência de 512 bytes em `0x08F7D438`. A fonte define
acesso direto aos índices 32–255 no renderer latino US. O relatório separa
essa correspondência de bytes de qualquer alegação de execução em runtime.

O atlas extraído foi inspecionado visualmente. Os 24 glifos
`áéíóúâêôãõçàÁÉÍÓÚÂÊÔÃÕÇÀ` existem e apresentam acentos no atlas latino.
O arquivo `message_latin_accents_preview.png` mostra esses índices, 12 por
linha, com escala inteira 4× e paleta de diagnóstico de alto contraste.
Os outros PNGs mantêm a paleta cinza do parser, que permite reconstrução
dos índices; nenhuma dessas cores pretende reproduzir a paleta do jogo.

Isso evita criar novos glifos latinos sem necessidade, mas não fecha os outros
renderers. `EncodeSmallFontString` só mapeia dígitos, letras ASCII e nove sinais.
A fonte possui 45 glifos, maiúsculas/minúsculas compartilham índices, e acentos
não são mapeados. A análise dessa função indica ainda que um caractere sem
caso mantém o índice anterior, portanto não existe fallback de acentos seguro.
Precisamos adicionar mapeamento/glifos e testar seus consumidores, ou escolher
outro renderer explicitamente para cada tela. A fonte `background_small`
permanece sem mapeamento semântico estabelecido.

Nos créditos, o parser textual usa CP932. Esse codec não representa os acentos
PT-BR requeridos; a mera existência de 524 glifos e larguras não resolve isso.
As páginas/códigos e o consumidor dos créditos ainda precisam ser mapeados para
definir novos códigos, glifos e métricas, mantendo os comandos do script.

## Pilotos e limites concretos

Uma investigação inicial identificou `gYesChoiceText`: “Sim” ocupa os mesmos
8 bytes que a origem, com `{END}` inalterado, e tem avanço 14px contra 18px.
Há 10 ocorrências alinhadas de seu endereço na ROM, apenas candidatas a
referências, e um consumidor fonte em `ms_charge.c`. Nenhuma ROM foi alterada
por essa investigação. O par “Não” não cabe nos 6 bytes reservados à origem
de `gNoChoiceText`; exige estratégia específica, não anexação à ROM de 32 MiB.

O primeiro piloto executável usa somente `us/event_text/gEvent000Text00`,
cuja cena original foi alcançada pelo harness separado de runtime. A ferramenta
não aceita IDs ou traduções arbitrários:

```sh
.venv/bin/python tools/probe_dialogue.py \
  --rom private/rom/B8CE.gba \
  --out private/rom/B8CE-dialogue-probe.gba \
  --report private/reports/dialogue-probe.json
```

A candidata contém “Não há ninguém aqui.” e preserva `{END}`. Usa 42 dos
52 bytes originais, mantém os 10 bytes restantes intactos e reduz o avanço
derivado da tabela latina de 126px para 100px. Nenhum dado foi realocado;
os bytes fora da substituição, ponteiros e tamanho integral permanecem iguais.
O SHA-256 observado é
`cbce000cd40649be6cb8aeebfd21282eca2d71509c2e59e2d6258d1fa9375ce5`.

O relatório de geração marca `awaiting_matching_runtime_capture` e
`release_approved=false`: não presume testes futuros. Depois, o harness
libmgba 0.10.5 executou exatamente esse hash por 12.000 frames em macOS arm64,
com o trace da cena original. A captura privada
`private/runtime/dialogue-ptbr-main/frame-12000.png` foi inspecionada: mostra
a fala completa, ã/á/é legíveis e nenhum corte visível. O relatório do harness
registra o SHA da candidata, ROM em memória inalterada e framebuffer SHA-256
`25f177c5e0e40c98aeddde0b00ac19a91e190c7bbcf0539f11f8ef05af5f5dd1`.
Também foi gerado e reaplicado um BPS privado de 92 bytes, com o mesmo SHA
da candidata; isso não aprova sua distribuição.

Essa evidência fecha apenas a exibição dessa fala naquele instante, incluindo
os três acentos presentes. Não certifica continuação, todos os consumidores,
referências para o
interior de strings, o resto das falas, ambas as campanhas ou cobertura 100%.
A reinserção geral continua bloqueada. Uma aprovação de renderer deve ser
anexada à sua fonte/consumidor/caixa e à revisão testada, sem virar uma flag global.

## Verificação automática

Oito testes sintéticos usam os parsers upstream reais para 4bpp/2bpp,
round-trip PNG, endianness u16, ponteiros errados, OAM não suportado, métricas
divergentes, recursos truncados e limites da ROM. Não incluem assets do jogo:

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_graphics.py' -v
```

Na ROM fornecida, as cinco fontes passaram o round-trip; os três conjuntos de
ponteiros e as três tabelas de métricas foram verificados. A candidata de
diálogo foi também comparada separadamente contra a origem, incluindo tamanho,
bytes fora da substituição, hash e decodificação do texto reinserido.
