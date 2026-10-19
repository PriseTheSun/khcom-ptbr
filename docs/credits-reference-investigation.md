# Referências das fontes de créditos: investigação estática inicial

O registro abaixo preserva a investigação estática anterior à execução.
O contrato do agendador, os IDs de filme 4/5 e o ensaio privado nas duas
variantes foram posteriormente verificados em [credits-mode-entry.md](credits-mode-entry.md).
Esse ensaio usou três escritas diagnósticas de RAM, mantendo a ROM intacta;
observou 627 das 631 entradas antes do término original por tempo. As
limitações de fechamento global de consumidores e de espaço livre abaixo
continuam aplicáveis.

Esta investigação usa a ROM USA B8CE rev0 de SHA-256
`6f6e7b61bb7b6ef7e2bea6e9dd01e70570a715835cc3713abe86186fd2c4e28d`,
o commit khcom `5dc49b75068bfe24e07bdaf365570d64682680c3` e os fontes
já fixados em `manifests/upstream.json`. Não modifica ROM, save ou RAM do jogo.
O relatório detalhado está em `private/reports/credits-reference-v1/report.json`;
ele preserva hashes de fontes, trechos de ROM, decoder e helper privado.

## Resultado que muda a próxima implementação

A auditoria do roteiro original usa 63 índices na fonte 0 e 58 na fonte 1;
a união tem **70 índices**. Há **454 índices ausentes de ambos os conjuntos**.
O bloco 210–233 é um exemplo de 24 candidatos consecutivos: corresponde aos
códigos existentes `82A0`–`82B7`, não aparece nos trechos desenhados pelo
roteiro US e mantém os tamanhos dos arrays. Isso não aprova a substituição:
a ausência observada pertence a esse roteiro, não a todos os consumidores.
O índice 0 continua reservado à semântica original de espaço/fallback e ao
preenchimento das bordas do renderer.

**1.200 bytes é crescimento líquido, não o tamanho necessário para uma
realocação direta.** Os quatro arrays expandidos têm estes tamanhos:

| Array | Atual, 524 glifos | Ampliado, 548 glifos |
|---|---:|---:|
| Bitmap fonte 0, 8×16 2bpp | 16.768 | 17.536 |
| Bitmap fonte 1, 8×8 2bpp | 8.384 | 8.768 |
| Larguras fonte 0 | 524 | 548 |
| Larguras fonte 1 | 524 | 548 |
| Total | 26.200 | 27.400 |

Sem uma extensão adjacente comprovada, a realocação por cópia precisa acomodar
os arrays completos, possivelmente em quatro regiões. Obter apenas 1.200 bytes
exigiria mover/compactar proprietários vizinhos ou mudar o renderer para dados
segmentados. Isso aumenta a quantidade de referências e consumidores a provar.
Font0 termina onde Font1 começa; Font1 termina onde começam as páginas. As
larguras também têm proprietários imediatamente seguintes. O mapa de assets
não encontrou nem aprovou espaço livre para essas mudanças.

## Âncoras nos bytes e instruções ARM7TDMI/Thumb

O decoder Thumb do mGBA 0.10.5 já usado pelo projeto foi empregado em um helper
privado de leitura. Ele não executa a ROM nem altera o build de produção. Os
dumps lineares incluem pools de literais; linhas decodificadas nesses pools
não são afirmações de código executável. A identificação abaixo decorre da
correspondência entre instruções, constantes/layout e funções C fixadas;
ainda não é uma captura de chamadas no core nem uma reconstrução matching.

| Papel na fonte fixada | Entrada Thumb, endereço sem bit T |
|---|---|
| `SrollTextGetGlyphIndex` | `0x08115F34` |
| `SrollTextGetGlyphWidth` | `0x08115F8C` |
| `SrollTextMeasureWidth` | `0x08115FBC` |
| `SrollTextGetGlyphAddress` | `0x08116008` |
| `SrollTextBlitGlyph` | `0x08116034` |
| `SrollTextSelectFont` | `0x081160EC` |
| `SrollTextInit` | `0x0811614C` |
| `SrollTextEnqueueChar` / `EnqueueString` | `0x081161EC` / `0x081167F8` |
| `SrollTextProcessNextChar` | `0x0811683C` |
| `SrollTextDrawStringAtPixelX` | `0x08116BEC` |
| `SrollTextMapSingleByteChar` | `0x08116CDC` |

O único valor u32 alinhado igual a `gStaffRollFonts` (`0x09A5B440`) está em
`0x08116148`. O LDR Thumb em `0x081160F8` o carrega; a rotina limita a seleção
a 0/1, calcula stride 24 e copia os campos de `SrollFont`, coincidindo com a
fonte C. O mapa de byte simples (`0x09A5B470`) tem literal em `0x08116CE8`,
carregado em `0x08116CDE`. Os quatro ponteiros de bitmaps/larguras aparecem
nos campos esperados de `gStaffRollFonts`, como já verificado pelo assetgen.

A busca de encodings BL em toda a ROM encontrou somente uma chamada ao Init,
em `0x08113298`; sete ao MeasureWidth, no produtor dos créditos; e cinco ao
DrawStringAtPixelX, também no produtor. As chamadas de GetGlyphIndex,
GetGlyphAddress, EnqueueString e Blit permanecem dentro da cadeia prevista.
Não apareceram palavras alinhadas iguais às 16 entradas examinadas, com ou
sem o bit Thumb, nem branches Thumb curtos para suas entradas. Os locais e
hashes estão no relatório. Isso fortalece a delimitação, mas a varredura não
prova limites de todas as funções, referências desalinhadas, saltos para o
meio de funções ou endereços calculados.

Nos **12 arquivos C/header fixados examinados**, as chamadas à API textual
aparecem no produtor e no próprio renderer. Isso não foi uma busca de toda a
árvore upstream. `sroll_a_name.c` usa blocos gráficos e animações próprios
para nomes/cargos; não deve ser confundido com um consumidor desses bitmaps
de fonte. Seu texto em imagens mantém uma tarefa de cobertura separada.

## Como chegar aos créditos no core

Há uma âncora concreta de entrada: o nome `mode_StaffRoll`, em `0x09A54208`,
é referenciado pelo descritor em `0x09EFA9C4`, seguido dos ponteiros Thumb
`0x08112B3D`, `0x08114325` e `0x08114715` para inicialização, atualização e
saída. Esses bytes correspondem à declaração final de `mode_staffroll.c`.

Um consumidor em `0x0805F0A8` carrega esse descritor e chama `0x080010CC`
com argumento zero. O corpo desta última rotina escreve o descritor em
`0x03007494` e o argumento em `0x03007498`; a atribuição funcional de
agendamento precisa ser fechada com o dono do loop de modos. O ramo de entrada
lê `0x0203493C` e chega aos créditos para valores 4/5, mas esses valores ainda
não foram ligados ao produtor de evento numa fonte fixada. **Não usar esses
endereços como receita de alteração de RAM.** Eles são âncoras para leitura,
breakpoints e fechamento do contrato de transição.

A entrada normal pelo jogo continua sendo a conclusão de campanha e seu
encerramento. O save demonstrado em M1 é do começo de Sora; não permite alegar
acesso aos créditos ou término de Riku. Não foi obtido save de terceiros.

Para uma prova de renderer anterior à conclusão das campanhas, a rota
prática é um **ensaio privado de entrada de modo**, após verificar a sequência
de descarte/inicialização do agendador. Esse futuro ensaio precisa registrar
explicitamente a alteração diagnóstica de estado e não pode valer como prova
de progressão normal ou save/reload. Entrar pela inicialização real do modo
preserva a configuração de VRAM, tarefas e áudio; saltar diretamente para
`StaffRollRunCredits` omitiria requisitos de inicialização.

O modo começa com espera, cenas e áudio, depois chega à rolagem. Sora/Riku
selecionam scripts de personagens e imagens diferentes pelo estado do jogo.
O roteiro de linhas US é compartilhado, mas ambos os percursos precisam ser
capturados. O código US usa `STAFFROLL_SCROLL_FRAMES = 0x431C` (17.180) no
relógio de música; isso orienta o orçamento de execução, sem prometer o frame
exato de cada linha nem a duração total até a tela final.

## Experimento delimitado recomendado

1. Fixar e revisar o dono do agendador e do consumidor em `0x0805F0A8` no
   manifesto único. Fechar a sequência de saída do modo anterior, reset de
   tarefas/allocators e entrada real dos créditos; documentar as dependências
   de estado e o seletor Sora/Riku. Não escrever ROM nem criar patch nessa etapa.
2. Em build diagnóstico separado, registrar chamadas às âncoras de Init,
   SelectFont, DrawStringAtPixelX e GetGlyphIndex. Cada evento deve incluir
   PC/LR, ponteiro do contexto, fonte por ponteiros de glyphs/widths, endereço
   da string, código e índice; buffers devem ter limites e detectar perdas.
3. Executar o original nas duas variantes de diagnóstico até terminar a
   rolagem, sem pular linhas. Comparar a sequência de strings/estados de fonte
   com o ledger de 631 entradas e registrar códigos de preenchimento de borda.
   Capturar as duas fontes e as três linhas com avisos de avanço. A igualdade
   deve ser por sequência e endereço, não somente pelo número de glifos.
4. Em paralelo, fechar a busca de produtores/referências fora dos 12 arquivos
   já examinados e validar os callers nos bytes da ROM. O ensaio dinâmico
   sozinho não prova ausência de outro consumidor.
5. Se essa análise fechar o conjunto de entradas possíveis e os 24 índices
   permanecerem inalcançáveis, escolher o reuso e implementar um codec de
   créditos PT-BR com round-trip original e aliases explícitos. Caso contrário,
   preparar realocação dos arrays com referências e ocupação comprovadas.

Critério do próximo gate: contrato de entrada demonstrado, trace original
completo e sem perda nas duas variantes, correspondência com o ledger e
referências estáticas pendentes explicitamente resolvidas ou preservadas como
incógnitas. Só depois produzir os 48 desenhos e métricas de um piloto privado.
Nenhum dos 454 índices ou dos intervalos desconhecidos do mapa foi declarado
livre; esta investigação não altera as tarefas de cobertura integral.
