# Créditos: entrada e rolagem observadas no core

O ensaio privado executou os filmes finais e a rolagem dos créditos nas
variantes Sora e Riku usando a ROM USA B8CE rev0 original. **Foi uma entrada
diagnóstica por três escritas de RAM, não conclusão normal das campanhas.**
Não houve edição da ROM, de glifos ou de saves em disco. O executável privado
usa a biblioteca mGBA já fixada pelo projeto; o app e o core de produção não
receberam instrumentação.

As duas variantes observaram o inicializador real de `gModeStaffRoll`, seguido
da inicialização textual, das duas fontes e de toda a fase de rolagem até o
encerramento por tempo. Isso permite experimentar posteriormente os glifos de
créditos em um consumidor real. Não autoriza ainda substituir índices ausentes
do roteiro, nem fecha cobertura de localização, imagens ou progressão.

## Identidade e evidências

- ROM de 32 MiB, SHA-256
  `6f6e7b61bb7b6ef7e2bea6e9dd01e70570a715835cc3713abe86186fd2c4e28d`.
  O arquivo, o buffer de entrada e a imagem de ROM dentro do core mantiveram
  essa identidade. SHA-1 conhecido: `10729bd884f8fdca7a310b6d606c52e46657aa48`.
- Fontes khcom no commit `5dc49b75068bfe24e07bdaf365570d64682680c3`.
  Oito novos arquivos foram fixados com backup, comparação do Git blob SHA-1
  à árvore da API e SHA-256 do conteúdo; `verify_upstream()` passou com os
  107 arquivos então fixados. Essa contagem é histórica e não limita a
  aquisição posterior para auditoria de consumidores.
- Fontes, helper, binários, dumps Thumb e hashes ficam em
  `private/reports/credits-entry-v1/evidence.json`. Os resultados finais estão
  em `trace-v2-sora/` e `trace-v2-riku/`; execuções anteriores foram preservadas.
- A biblioteca veio do arquivo mGBA 0.10.5 fixado pelo projeto. Seu campo
  `projectVersion` informa literalmente `0.10-main-1-6c7971b-dirty`; esse valor
  foi preservado, sem substituí-lo por um rótulo idealizado. A proveniência
  usa os hashes do arquivo de origem, dos fontes e da biblioteca efetiva.

O helper privado `trace-v2.cpp` chama `core->step` e observa o PC Thumb efetivo,
sem inserir breakpoints na ROM ou redirecionar o PC. O trace de texto admite
131.072 eventos e falha ao exceder esse limite; os limites de espera também
falham explicitamente. Foram gravados 17.068 eventos por variante, sem perda.
A verificação privada reproduzível `verify-trace.py` confronta os traces com
os bytes da ROM e com `credits-audit-v2.json`, incluindo hashes e ordem.

## Contrato de entrada

A atribuição das funções combina instruções ARM7TDMI/Thumb, descritores e
fontes fixadas. Os dumps lineares incluem pools de literais; não representam
uma prova de código em cada byte. O agendador está em
[mode.c](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/src/mode.c#L81),
chamado pelo loop de
[main.c](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/src/main.c#L169).

| Âncora | Endereço sem bit Thumb |
|---|---:|
| `ModeStart` | `0x08000FB4` |
| `ModeRequest` | `0x080010CC` |
| `ModeUpdate` | `0x08001100` |
| Saída do título | `0x080D622C` |
| Inicializador de filme | `0x0805E8B4` |
| Consumidor que solicita os créditos | `0x0805F0A8` |
| Inicializador de créditos | `0x08112B3C` |
| `SrollTextInit` | `0x0811614C` |
| `SrollTextSelectFont` | `0x081160EC` |
| `SrollTextDrawStringAtPixelX` | `0x08116BEC` |
| `SrollTextGetGlyphIndex` | `0x08115F34` |

O título foi inicializado normalmente, sem entrada de teclas, até o estado
`PRESS_START` (5). Na entrada de `ModeUpdate`, o helper exigiu o modo título,
nenhum pedido pendente, flags de modo exatamente 8, ausência de callback de
transição, ausência de override de VBlank, link desativado e execução fora de
VBlank. Somente então fez estas três escritas, registrando antes e depois:

| Campo | Endereço | Antes | Sora | Riku |
|---|---|---:|---:|---:|
| Flags de campanha | `0x02039BB8` | 0 | 0 | 8 |
| Argumento pendente | `0x03007498` | 0 | 4 | 5 |
| Descritor pendente | `0x03007494` | 0 | `0x09EDE4D0` | `0x09EDE4D0` |

O primeiro valor controla exclusivamente o bit `GAME_FLAG_RIKU` no helper;
na variante Sora a escrita não muda o valor. Os outros dois reproduzem os
campos escritos por `ModeRequest(&gModeMovie, id)`. Nenhuma flag de heap reset,
pilha ou registrador da CPU foi forçada.

O agendador executou a saída do título e iniciou o filme. Os IDs 4 e 5 são
`MOVIE_ENDING` e `MOVIE_RIKU_ENDING` na
[declaração fixada](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/include/evt/mode_movie.h#L22).
O próprio
[consumidor de filmes](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/src/evt/mode_movie.c#L825)
executa a reprodução, encerra o filme, restaura heaps/display/áudio e solicita
`gModeStaffRoll` com argumento zero. O trace observou o início bem-sucedido do
filme, seu retorno, a saída desse modo, a entrada dos créditos e o retorno de
seu inicializador ao agendador. A preparação de áudio/VRAM/tarefas decorre
dessa cadeia real; não houve chamada direta à função de rolagem.

## Resultados das duas variantes

Frames são do contador do core, desde reset. Os valores diferentes entre as
variantes decorrem de seus filmes/cenas, não de saltos aplicados pelo helper.

| Evento | Sora | Riku |
|---|---:|---:|
| Pedido diagnóstico | 953 | 953 |
| Inicializador dos créditos | 4.528 | 4.110 |
| Início da fase textual | 10.323 | 9.905 |
| Término da rolagem por tempo | 21.882 | 21.461 |
| Saída da fase textual após espera | 22.004 | 21.583 |
| Linhas observadas, índices 0–626 | 627 | 627 |
| Chamadas de desenho | 388 | 388 |
| Chamadas código → índice | 16.046 | 16.046 |
| Seleções de fonte, incluindo inicialização | 5 | 5 |

Todos os ponteiros de linha correspondem ao array original, na ordem esperada.
Todos os desenhos correspondem ao ledger por bytes, fonte, X, Y e ponteiro
direto para o trecho da string. A amostra US não usa o ramo de duas colunas
com buffer gerado na RAM; esse ramo mantém apenas prova estática/testes
sintéticos. Todas as conversões de código para índice coincidem com as
entradas previstas, inclusive o glifo zero usado no preenchimento.

As seleções são fonte 0 no Init, fonte 1 na linha 153, fonte 0 na 170,
fonte 1 na 264 e fonte 0 na 278. Os pares glyphs/widths observados são
`0x09A54D00`/`0x09A54500` e `0x09A58E80`/`0x09A5470C`.
Os conjuntos dinâmicos têm os mesmos 63/58 índices do ledger estático completo.
Os candidatos 210–233 não foram usados nesse percurso. Isso não prova sua
inacessibilidade por outros consumidores ou outros dados.

Há **631 entradas estáticas e 627 entradas visitadas**. Nas duas variantes,
a transição para espera ocorreu com `musicFrames = 17.180` e `flags = 0`.
Isso corresponde ao teste de tempo de
[StaffRollRunCredits](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/src/sroll/mode_staffroll.c#L3682),
também conferido no ramo Thumb. As entradas 627–630 são duas repetições de
espaço/branco; o sentinela NULL no índice 631 não é visitado. O helper não
prolongou o relógio para alcançá-las. Os 392 desenhos previstos pelo ledger
incluem quatro chamadas vazias/espaço que ficam após esse término.

As capturas privadas `row-12.png`, `row-169.png`, `row-267.png` e
`row-540.png` mostram as duas fontes em ambas as variantes. Foram feitas dez
linhas depois do carregamento do alvo para colocá-lo dentro da tela. As linhas
169/267/540 têm avanços calculados para X=6..234, 13..227 e 6..233. O conteúdo
aparece nas capturas; personagens podem sobrepor parte da linha. Um aviso da
janela estática 16..224 não estabelece sozinho recorte visível, nem substitui
comparação dos pixels e estado efetivo de janela. As imagens permanecem
privadas porque contêm conteúdo original.

## Limites e próxima alteração delimitada

O ensaio termina ao sair da fase textual para a fase seguinte, sem verificar
o retorno final ao título, créditos completos em imagens, áudio ouvido ou
progressão normal de qualquer campanha. O campo conservador
`complete_text_trace: false` do relatório básico foi preservado; a cobertura
exata desta execução está em `text-summary.json` e `comparison.json`, não em
uma aprovação genérica de completude. O ledger de origem continua marcado
como derivado de fonte; a evidência runtime é um artefato separado.

A execução foi medida com `/usr/bin/time -l`: Sora 9,77 s de parede,
9,27 s de usuário, 0,05 s de sistema; Riku 9,49/8,99/0,05 s. Ambos registraram
RSS máximo de 75.071.488 bytes. Foram execuções independentes concorrentes,
sem classificação controlada frio/quente; não são benchmark do app. Custo
de tokens não foi medido.

O próximo passo é fechar a busca estática dos consumidores e entradas
possíveis, confrontando os callers com os bytes da ROM. Se essa análise
aprovar reuso de índices, preparar um piloto privado com os 24 caracteres
PT-BR em cada fonte (48 desenhos), métricas e codec explícitos, e repetir
estas duas sequências contra o original. Se o conjunto não puder ser fechado,
a alternativa de realocação precisa comprovar ocupação e referências dos
arrays completos. Nem este ensaio nem pixels uniformes estabelecem espaço
livre. Nenhuma tradução em massa ou mudança de glifo foi feita aqui.
