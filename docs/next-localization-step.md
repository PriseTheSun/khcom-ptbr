# Próxima implementação de localização

O próximo trabalho é fechar o mapa de consumidores e um piloto de créditos,
antes de ampliar qualquer atlas. Não surgiu necessidade de mudar a arquitetura
libmgba + SDL + BPS nem de pedir uma decisão nova ao usuário. Os detalhes abaixo
são investigação técnica executável dentro de M1/M2, não dependências externas.

## Evidência e alcance

Foi pesquisado o conteúdo dos 269 arquivos C em `src/` do commit
[`5dc49b75068bfe24e07bdaf365570d64682680c3`](https://github.com/Pheenoh/khcom/tree/5dc49b75068bfe24e07bdaf365570d64682680c3).
Os usos abaixo são correspondências de símbolos no código-fonte, sem alegação
de call graph completo, endereços de função reproduzidos por build matching
ou alcance comprovado em runtime. A ROM local continua a revisão USA validada.
Esta investigação não alterou ROMs nem implementou tradução em massa.

O atlas latino já contém os **24** caracteres
`áéíóúâêôãõçàÁÉÍÓÚÂÊÔÃÕÇÀ`. A rodada `private/fonts/us-v3/` acrescentou à/À
à matriz visual, preservando v2. `private/fonts/us-v4/` mantém os mesmos pixels
e explicita a diferença entre início do recurso e início dos tiles: a entrada
`sprite_sheet` inclui registros de frames/animações antes dos tiles.
`manifest_resource_address` não deve ser usado como ponteiro runtime de tiles.
Os oito testes gráficos passaram novamente, incluindo essa distinção.

## Fonte pequena: primeiro identificar a superfície real

Em [`src/msg/msg.c`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/src/msg/msg.c),
há rotas diferentes que não podem ser agrupadas pelo nome “small”:

| Rota produtora → consumidora | Observação fonte |
|---|---|
| `EncodeSmallFontString` → `DrawSmallFontString` | 45 índices: dez dígitos, 26 letras ASCII compartilhadas entre maiúsculas/minúsculas, nove sinais; avanço fixo de 8px |
| `AddSpriteTextLine` → `DrawSpriteTextLines` | Usa o mesmo atlas de 45 glifos, mas possui outro mapper; entrada limitada a 16 caracteres; não compartilha a implementação de `EncodeSmallFontString` |
| `SetBgTextLine` → `DrawBgTextLines` | Consome pares de bytes SJIS; escolhe bancos/fontes conforme altura; o ramo ≤8px usa `gBgTextSmallFontFrames`, com mapeamento restrito |
| `SetSpriteTextSlotAscii` → `DrawSpriteTextSlots` | Usa frames de `gMsgFontBank0`, não `gSmallFontTiles`; armazena até 16 caracteres e avança 10px |

Os consumidores diretos de `EncodeSmallFontString`/`DrawSmallFontString`
encontrados fora de `msg.c` foram:

- [`card_prize_card_init.c`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/src/card/card_prize_card_init.c#L1030): overlay de versão (`Version_0`, `Version_1`).
- [`map_tasks.c`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/src/map/map_tasks.c#L1890): debug de seed/código/cursor de mapa.
- [`mode_eventselect.c`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/src/evt/mode_eventselect.c#L1070): contador de frames do seletor de eventos.

Não foram encontrados chamadores C externos de `AddSpriteTextLine`,
`SetBgTextLine`, `SetBgTextLineNumber`, `SetSpriteTextSlotAscii` ou
`SetSpriteTextSlot`. Isso é evidência de busca fonte, **não prova de ausência
de chamadas indiretas ou de código fora da reconstrução**. Não devemos ampliar
o atlas de debug e declarar que o menu normal foi resolvido.

Há um menu concreto para o próximo teste: nomes de baralhos. Em
[`card_deckmenu2.c`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/src/card/card_deckmenu2.c#L5135)
e [`card_deckmenu2_riku.c`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/src/card/card_deckmenu2_riku.c#L818),
o produtor chama `LoadTextSlots(GetDeckName(...))`; na versão US, essa função
seleciona `LoadLatinTextSlots`. `SetDeckName` copia code units de dois bytes
em US. O editor copia 20 bytes e força os bytes 18/19 a zero: esse caminho
oferece até nove code units de nome, além de exigir largura/caixa e save
verificados. Os três nomes padrão do catálogo usam `game`, reserva original
14 bytes cada. Não presumir que nomes de baralho US usem CP932 ou fonte pequena.

Para ampliar realmente o atlas de 45 glifos, a conta depende do contrato
tipográfico comprovado na tela: preservar seu estilo sem distinção de caixa
exigiria 12 desenhos acentuados compartilhados por 24 códigos de entrada;
renderizar as 24 formas acentuadas distintamente exige 24 desenhos. Se também
for necessário distinguir todas as letras ASCII minúsculas hoje compartilhadas,
acrescentam-se 26 desenhos, totalizando 50 novos glifos e 95 índices.
Um glifo simples 8×8 4bpp custa 32 bytes de tiles, 10 de frame e 4 de ponteiro:
estimativas sem deduplicação de 552/1.104/2.300 bytes para 12/24/50 glifos,
além de código e ajustes de capacidade. Não reservar esse espaço antes de
confirmar qual renderer será usado. Também seria necessário atualizar os dois
mappers, tamanho carregado por `LoadSmallFontTiles`, capacidade OBJ e a geometria
dos acentos dentro de oito linhas.

## Créditos: rota identificada e extensão sem trocar o renderer

O produtor é `StaffRollRunCredits`, em
[`mode_staffroll.c`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/src/sroll/mode_staffroll.c#L3468).
Ele interpreta prefixos de roteiro (`#` troca fonte, `@` cor, `~` separação,
`=/-/+` alinhamento, entre outros), mede a linha e chama o renderer. Esses
prefixos são sintaxe, não prosa a traduzir.

O consumidor completo está em
[`sroll_tmr.c`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/src/sroll/sroll_tmr.c#L537):

1. `SrollTextMeasureWidth` e `SrollTextEnqueueString` leem bytes com bit 7
   como pares; bytes ASCII passam por `SrollTextMapSingleByteChar`.
2. `SrollTextGetGlyphIndex` usa uma tabela de páginas e um byte por código
   para escolher índice; entradas ausentes retornam índice 0.
3. `SrollTextSelectFont` seleciona uma das duas estruturas `SrollFont`.
4. `SrollTextGetGlyphWidth` e `SrollTextGetGlyphAddress` escolhem largura e
   bitmap; `SrollTextProcessNextChar` chama o blitter e atualiza tiles/mapa.

Isso não é um decoder CP932 completo: por exemplo, não se pode pressupor que
todo byte simples de CP932 com bit 7 seja consumido como byte simples pelo jogo.
Um codec de edição próprio para créditos deve reproduzir precisamente essas
regras e preservar o conjunto original, em vez de trocar tudo por CP1252.

Foram conferidos contra a ROM, usando `assetgen.check_record`, os quatro
registros abaixo, além das fontes e larguras já verificadas no spike:

| Registro | Endereço | Bytes |
|---|---|---:|
| `gStaffRollFontPages` | `0x09A5AF40` | 512 |
| `gStaffRollFontCodes` | `0x09A5B140` | 768 |
| `gStaffRollFonts` | `0x09A5B440` | 48 |
| `gStaffRollSingleByteCharMap` | `0x09A5B470` | 512 |

As páginas 0x81–0x84 cobrem respectivamente 147, 145, 134 e 98 índices,
totalizando 524. Há 244 células com sentinel 0xFF (45/47/58/94 por página).
São códigos sem mapeamento, **não espaço livre de tiles nem autorização para
reusar glifos existentes**. Os dois atlas têm somente o glifo 0 sem pixels;
esse índice participa de espaço/fallback e não é uma reserva disponível.

O repertório novo precisa de 24 códigos e 24 desenhos por estilo: **48 desenhos**
nos formatos 8×16 e 8×8. Acrescentá-los ao fim dos dois atlas exige 768 + 384
bytes de bitmap e 48 bytes de larguras, total 1.200 bytes, sem contar alinhamento
ou mudança de tabelas. Os contadores passariam de 524 para 548. Há capacidade
lógica em páginas existentes, mas ainda precisamos selecionar e comprovar
24 códigos que não conflitem com roteiro, dados originais ou outro consumidor.

Uma alternativa técnica a investigar primeiro é reaproveitar índices realmente
inalcançáveis, preservando os tamanhos atuais. A simulação fonte do mapeamento
para os 255 itens do pool de créditos encontrou 78 índices na união dos bytes
originais, incluindo prefixos como se fossem caracteres, sem fallback. Sobram
446 índices **não observados nesse conjunto**, candidatos a investigação.
Isso não é prova de que sejam reutilizáveis: faltam a ordem real dos ponteiros
do roteiro, estados de fonte, todos os produtores e referências, além de teste
do caminho completo. Reuso só será escolhido após essa prova; caso contrário,
alocação interna verificada continua o caminho previsto.

Há limites concretos a modelar antes da tradução: o ramo `~` usa `buf[80]`,
com até 76 bytes antes do primeiro separador quando acrescenta três espaços e
terminador, e até 79 bytes no segundo trecho antes do terminador. A fila tem
256 entradas u16; sua ocupação real precisa ser derivada das rotinas produtoras.
O texto usa um mapa de 30 tiles de largura, mas a janela visível é configurada
entre x=16 e x=224; medir apenas contra 240px não prova ausência de corte.
Esses limites vêm de fonte e ainda devem ser confirmados no caminho runtime.

## Como chegar às funções e referências na ROM

As tabelas já verificadas fornecem âncoras melhores que buscas de strings.
No atlas pequeno, o recurso começa em `0x090D3FB4`, os tiles começam realmente
em `0x090D4180` e a tabela de frames fica em `0x09EEC538`. Uma varredura de
valores u32 alinhados encontrou candidatos aos literais de tiles em
`0x08062F10`/`0x08066900` e de frames em `0x08062F0C`/`0x08066E3C`.
Ainda não são endereços certificados de funções ou uma lista completa de xrefs.
O próximo passo é interpretar os LDR PC-relative e os BL em Thumb/ARMv4T ao
redor dessas âncoras, confirmar limites de função e exercitar breakpoints de
leitura no harness/debugger. Ponteiros calculados exigem rastreamento próprio.

Nos créditos, a identidade dos ponteiros de glyphs/widths em
`0x09A5B448/44C` e `0x09A5B460/464` já é comprovada pelo layout de
`gStaffRollFonts`. Eles são também as únicas ocorrências u32 alinhadas desses
quatro endereços de payload na varredura realizada; isso não exclui referências
calculadas. Os atlas são adjacentes: o fim do font0 é o começo do font1, cujo
fim é o começo das páginas. Expandir em posição fixa sobrescreveria dados
identificados. Realocação exige mapa desses proprietários, todas as referências
e uma região realmente reutilizável; não basta encontrar bytes uniformes.

[`config/us/named_funcs.cfg`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/config/us/named_funcs.cfg)
fornece âncoras Thumb para o módulo de créditos, como `task_sroll_tmr_0` em
`0x081152A4`; não fornece a lista completa das funções de fonte acima.
`config/us/symbols.txt` contém apenas sete símbolos adicionais e também não
resolve isso. Uma reconstrução matching pode produzir mapa/ELF confiável após
comparação de bytes; alternativamente, usar as âncoras e rastreamento ARMv4T
com confirmação de instruções. A análise genérica ARMv7 do REA não substitui
essa validação.

## Próximo trabalho, em ordem

1. **Fixar proveniência dos novos produtores.** Acrescentar `sroll_tmr.c`, os
   consumidores de baralho e metadados necessários ao único manifesto upstream,
   com hashes; não criar outro dono de download/parser.
2. **Fechar um menu real.** Chegar ao nome do baralho no harness, identificar
   produtor/renderer, medir caixa e testar matriz latina de 24 acentos, destaque
   e save/reload. Registrar separadamente quais rotas compactas permanecem
   sem alcance comprovado. Não satisfazer o gate de menu com overlay de debug.
3. **Construir o parser de roteiro dos créditos.** Preservar prefixos, ordem
   `sStaffRollLines`, troca de fonte e cores; exportar contexto/limites; round-trip
   de bytes e testes de códigos ausentes, comandos e buffers de 80 bytes.
4. **Fechar referências e ocupação do subsistema de créditos.** Gerar ledger
   de índices usados por fonte e todas as referências. Demonstrar reuso de
   24 índices ou alocação interna para crescimento de 1.200 bytes; rejeitar
   sobreposição, pointers pendentes e qualquer expansão além de 32 MiB.
5. **Implementar um perfil de créditos PT-BR e atlas piloto.** Mapear 24 códigos
   a glifos/métricas de ambos os estilos; validar round-trip dos recursos,
   sintaxe intacta e caracteres não mapeados. Só então produzir candidata
   privada e BPS do piloto.
6. **Executar o piloto com os dois estilos e prefixos relevantes.** Comparar
   capturas, cortes/acentos, largura, cor, alinhamento e continuação; manter
   as etapas Sora/Riku/gráfico/vídeo ainda abertas até suas próprias provas.

Esse trabalho já está contemplado por tarefas 1.9, 2.5–2.9 e 2.14, pelo design
de codecs por domínio/ocupação de ROM, e pelos requisitos de
`graphics-and-fonts` e `text-localization`. O novo conhecimento refina a ordem
da implementação. Escolher códigos e uma região comprovadamente reutilizável
é uma decisão técnica local; não exige alterar o produto ou pedir permissão
para seguir o plano. Nenhuma tarefa de cobertura integral foi encerrada aqui.
