# Piloto de diálogo de Riku

O comando público gera uma única substituição fixa na segunda fala do prólogo:

```sh
.venv/bin/python tools/probe_dialogue.py --rom private/rom/B8CE.gba \
  --scene riku-opening \
  --out private/rom/riku-piloto.gba \
  --report private/reports/riku-piloto.json
```

A receita seleciona `us/event_text/gEvent149Text01` pelo ID e hash original.
Produz “Onde…onde estou…” com o mesmo terminador: 34 bytes na reserva de 36,
preservando os dois bytes restantes. O avanço passa de 102 para 98 pixels na
fonte latina verificada. A ROM continua com 32 MiB e todos os demais bytes
permanecem idênticos. O valor padrão de `--scene` continua `sora-opening`;
nenhuma entrada aceita texto livre ou dispensa validação de origem.

SHA-256 da candidata:
`6766fe2a9b5ca35399536ea1f9b04d0cae11bcf3628ac5c27233e8cd6bac14a0`.
O BPS privado de 77 bytes foi reaplicado pelo aplicador próprio ao mesmo SHA.

## Entrada e observação

Um helper privado usou o core mGBA 0.10.5 e os símbolos do build matching
integral. Após o título original ficar estável, alterou **somente** a palavra
RAM `0x02039BB8`, de `0` para `0x20` (`GAME_FLAG_SORA_CLEAR`). A alteração
habilita a escolha de campanha; não demonstra conclusão de Sora nem modifica
ROM ou arquivo de save. A entrada na campanha foi então feita com inputs
normais: Start, baixo para Riku, confirmação, escolha do primeiro slot.

O trace confirmou `TitleExitToChoice`, duas chamadas de `SetupRikuNewGame`,
uma entrada em `Mode_MenuNew_0` e `RequestEventMode(149)`. A segunda chamada
de setup ocorre no caminho real de confirmação do slot. `LayoutMsgGlyphsPage`
recebeu `0x0900F974` no frame 2058, com a fonte latina e a caixa inferior de
Riku. A captura no frame 2658 contém a linha completa. ROM original e candidata
usaram o mesmo helper, inputs e trace de eventos; a ROM em memória permaneceu
idêntica à entrada em cada execução.

Foram observados 406 pixels diferentes na linha de texto e 47 no indicador
animado de continuar. Todos os pixels fora dessas duas regiões são iguais.
A inspeção visual confirmou a linha inteira, sem corte, com o mesmo retrato e
cenário. A diferença do indicador foi mantida como observação; não foi ocultada
para alegar igualdade de toda a interface. A primeira tentativa de input antes
do término da entrada do título falhou; o segundo ensaio alcançou a fala ainda
em escrita, e o terceiro aguardou sua exibição completa. As tentativas foram
preservadas separadamente.

A evidência, hashes das fontes/ELF/lib/helpers, relatórios, traces e capturas
ficam em `private/reports/riku-entry-v1/evidence-v2.json`. O helper não altera
core/app de produção. Este resultado cobre uma ocorrência de diálogo de Riku
por entrada diagnóstica; não comprova progressão normal, revisão linguística
humana, toda a campanha, todas as caixas ou conclusão do gate M2.14.

Fontes do commit `5dc49b75068bfe24e07bdaf365570d64682680c3`:

- `src/title/title.c`: escolha Sora/Riku condicionada a `GAME_FLAG_SORA_CLEAR`.
- `src/title/mode_title.c`: `TitleExitToChoice` inicializa a campanha e MenuNew.
- `src/game_state.c`: inicialização real de flags, deck e progresso de Riku.
- `src/map/map.c`: confirmação de slot e requisição do evento 149.
- `src/evt/events/149_riku_b12f_opning.inc`: roteiro e ocorrência da fala.
- `src/msg/msg.c`: consumidor latino e paginação observados.
