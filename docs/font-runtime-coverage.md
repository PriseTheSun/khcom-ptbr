# Fontes: consumidores reais e cobertura dirigida

O atlas latino já contém os 24 acentos `áéíóúâêôãõçàÁÉÍÓÚÂÊÔÃÕÇÀ`.
A prova dirigida agora os observou em diálogo normal, diálogo destacado,
menu selecionado e menu atenuado. Os créditos têm uma receita separada para
suas duas fontes. Cada resultado abaixo pertence ao consumidor indicado;
nenhum deles declara todos os layouts ou toda a campanha aprovados.

| Consumidor | Evidência dos 24 acentos | Limite |
|---|---|---|
| `LayoutMsgGlyphsPage` + paleta marrom | 24 glifos, 945 pixels de tinta exatos | Uma posição de diálogo do evento 156 |
| Mesma rotina + paleta ciano | 24 glifos, 945 pixels de tinta exatos | Evento 156 com inicializador alternativo real |
| `LoadLatinTextSlots` → `DrawTextSlots`, selecionado | 24 glifos com ao menos uma ocorrência completa | Sora Rename/Review Decks |
| Mesma rota, atenuado | 24 glifos com ao menos uma ocorrência completa | Sora Review Decks |
| Créditos 8×16 e 8×8 | 96 ocorrências e 5.984 pixels exatos | Quatro linhas, duas variantes; [piloto V2](credits-pilot.md) |

## Diálogo e destaque

Quatro candidatas privadas substituíram somente a reserva de
`gEvent156Text00`: doze minúsculas ou doze maiúsculas, em cor normal ou
destacada. São diagnósticos, não traduções. A fonte, código, ponteiros, ícones
e demais bytes da ROM permaneceram intactos; a cauda de cada reserva foi
preservada. A rotina devolveu **12 glifos** em cada chamada.

O helper iniciou Riku pelo menu original após habilitar temporariamente a
escolha de campanha. A confirmação de slot fez seu setup real. Quando o jogo
requereu o evento 149, o helper mudou o argumento pendente para 156, antes do
inicializador do evento. As duas escritas RAM por execução foram registradas:
`0x02039BB8: 0→32` e `0x03007498: 149→156`. O trace confirmou
`InitMsgGlyphSpritesAltPalette5(0)` e a chamada do consumidor com o endereço
correto do texto. Isso não corresponde a progressão normal da campanha.

A comparação usa a posição `(72,108)` recebida pelo renderer, os avanços
originais e as paletas `gTextBrownPalette`/`gTextCyanPalette` localizadas no
ELF matching e lidas da ROM. Não procura uma posição que encaixe a captura,
não aprende as cores dos próprios acentos e não ignora pixels divergentes.
**48 ocorrências, 1.890 pixels de tinta, zero diferenças, zero sobreposições
e zero pixels extras** foram observados. Inventários vazio/parcial/duplicado,
um frame sem pixels e um pixel de tinta incorreto foram rejeitados. As quatro
capturas nativas também foram inspecionadas, incluindo maiúsculas e cedilha.

Evidência: `private/reports/dialogue-fonts-v3/verification.json` e
`evidence.json`. As fontes e o core têm hashes; cada candidata foi verificada
antes da execução e sua ROM em memória permaneceu igual à entrada.

### Tentativas que não contam como prova

As versões privadas V1/V2 permaneceram preservadas. Revelaram dois contratos:

- O evento 149 inicializa somente a paleta normal. Inserir `{HIGHLIGHT}`
  nessa ocorrência não constitui teste válido de destaque; eventos 011,
  003, 134 e 156 possuem inicializadores alternativos explícitos.
- `LayoutMsgGlyphsPage` consome `HIGHLIGHT`/`PLAIN` e processa a unidade
  seguinte na mesma iteração. Um controle imediatamente antes de `END`
  faz a rotina tratar esse terminador como glifo 0 e prosseguir na cauda.
  A receita válida usa `HIGHLIGHT + letras + END`; o estado da paleta é
  inicializado por chamada. O validador público de eventos agora rejeita
  `terminal_palette_control`, mesmo quando a sequência geral de comandos
  não mudou. Um teste com dados autorais cobre esse caso.

Nenhuma dessas tentativas alterou o código do jogo para esconder o problema.
O comportamento limita as edições admitidas pelo contrato do consumidor.

## Reuso da prova do menu

O [ensaio de nomes de baralho](menu-probe.md) já tinha 22 ocorrências e
Quick Save/reload com a ROM original. Um agregado novo verificou que todos
os 24 caracteres possuem pelo menos uma ocorrência **inteira e exata**
em cada paleta. As duas ocorrências encobertas pela mão continuam inexatas;
não foram retocadas nem contadas como desenhos completos.

`private/reports/font-consumers-v1/menu-reused-evidence.json` contém os
conjuntos por paleta, hashes e três recusas de inventário incompleto.
Não houve nova execução desse menu. Isso evita repetir uma prova já disponível
e preserva seu alcance: a fonte dos nomes é a latina, embora apareça num menu.

## Atlas compactos e inventário do executável

O build matching integral produziu 31.933 chamadas/desvios diretos ARM/Thumb
e 98.607 referências ABS32 verificadas contra os bytes finais. A seleção por
endereço resolvido, incluindo aliases, mostrou:

- `EncodeSmallFontString`: nove chamadas, pelos formatadores numéricos,
  overlay de versão e depuração de mapa; nenhum ponteiro ABS32 para a função.
- `DrawSmallFontString`: seis chamadas, pelo contador do seletor de eventos,
  overlay de versão e depuração de mapa; nenhum ponteiro ABS32 para a função.
- `AddSpriteTextLine`: somente duas chamadas de seu wrapper numérico.
  O wrapper e `InitSpriteTextLines` não têm chamadas ou ponteiros identificados.
- `SetBgTextLine`: somente uma chamada de seu wrapper numérico.
  O wrapper e `InitBgTextLines` não têm chamadas ou ponteiros identificados.
- `CreateVersionDisplay` não tem chamadas ou ponteiros identificados.

Os 25 símbolos e suas arestas estão em
`private/reports/font-consumers-v1/matching.json`, vinculados ao ELF/mapa/ROM.
O exame da fonte concorda: a fonte de 45 glifos tem ASCII e sinais numéricos;
o atlas de fundo com 30 glifos está na rota sem inicializador chamado.
Esses atlas não devem ser expandidos para declarar um menu normal localizado.
Ausência de relocação não é prova formal de ausência de chamadas calculadas,
endereços montados manualmente ou código dinâmico; o relatório mantém esse
limite. Nenhum texto de debug recebe isenção linguística automática aqui.

Ainda faltam contratos para todos os layouts, páginas, valores dinâmicos,
posições e sobreposições. A cobertura acima suporta a prova dirigida de
fontes; revisão tipográfica humana e cobertura integral continuam separadas.
