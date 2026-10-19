# Prova de acentos no menu de baralhos

O menu real de Sora foi alcançado a partir do save normal validado em M1.
Os 24 caracteres `áéíóúâêôãõçàÁÉÍÓÚÂÊÔÃÕÇÀ` foram inseridos pela interface
Rename, exibidos em Review Decks, gravados por **Quick Save** e recuperados
em processos novos com a **ROM original**, sem checkpoint. O save normal
usado como entrada permaneceu intacto. Esta é uma prova delimitada do nome
dos baralhos, não de toda a localização.

Os artefatos são privados: `private/menu-probe/verification.json` reúne hashes,
traces, capturas, relatórios e comandos de reprodução; os relatórios do harness
permanecem inalterados. ROMs, saves e capturas não pertencem à distribuição.

## Contrato identificado

A fonte fixada é o commit
[`5dc49b75068bfe24e07bdaf365570d64682680c3`](https://github.com/Pheenoh/khcom/tree/5dc49b75068bfe24e07bdaf365570d64682680c3).
Os hashes dos arquivos consultados estão no relatório privado e sua aquisição
usa o manifesto upstream do projeto.

- [`LoadDeckNameTexts`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/src/card/card_deckmenu2.c#L5138)
  carrega os três nomes com `LoadTextSlots(GetDeckName(...))`.
- [`LoadTextSlots` / `LoadLatinTextSlots`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/src/msg/msg.c#L2222)
  selecionam, na revisão US, códigos de dois bytes e índices latinos diretos
  para valores de 32 a 255. Os 24 desenhos já existem no atlas latino verificado.
- [`DrawDeckNames`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/src/card/card_deckmenu2.c#L4140)
  e Rename chamam
  [`DrawTextSlots`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/src/msg/msg.c#L2770),
  que aplica o avanço de cada glifo e desloca a origem vertical em −2 pixels.
  O estado selecionado e os demais nomes usam paletas diferentes.
- [`CopyDeckNameToBuffer` / `SaveDeckNameFromBuffer`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/src/card/card_deckmenu2.c#L6564)
  copiam 20 bytes, com os bytes 18/19 zerados. Isso admite nove code units mais
  terminador no buffer; porém
  [`AppendKeyboardChar`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/src/card/card_deckmenu2.c#L6624)
  só insere quando a contagem é ≤7. O limite efetivo da interface é **oito**.
  A tentativa de inserir o nono caractere foi rejeitada em runtime.

Esta cadeia é derivada da fonte. Não foi produzido um trace de PC/breakpoints
ou build matching para suas funções. A correspondência dos pixels e avanços
da fonte com as capturas nativas dá evidência adicional do renderer usado
nestas telas; não estabelece alcance de outras rotas de texto.

## Candidata e percurso executado

O helper privado `private/menu-probe/build_keyboard_probe.py` usou os parsers
existentes de ROM, catálogo e fonte. Ele verificou os textos originais, limites
e terminadores antes de substituir 24 células das duas primeiras linhas de
entrada do teclado, nos endereços `0x09035742` e `0x09035762`. A comparação
binária encontrou **24 bytes alterados** em uma ROM que continua com 32 MiB.
Código, atlas, ponteiros, demais bytes e save de entrada não foram editados.

Os rótulos visuais das teclas continuam ASCII: esta candidata apenas remapeia
os caracteres produzidos pelo teclado e **não é um teclado localizado pronto**.
Os três nomes foram digitados pelo jogo, sem edição de SRAM:

| Baralho | Nome | Code units | Avanço | Pixels ocupados em Rename, `[x0,y0,x1,y1)` |
|---|---|---:|---:|---|
| 1 | `áéíóúâêô` | 8 | 45 px | `[138,16,183,26)` |
| 2 | `ãõçàÁÉÍÓ` | 8 | 43 px | `[138,15,181,28)` |
| 3 | `ÚÂÊÔÃÕÇÀ` | 8 | 47 px | `[138,15,185,28)` |

Essas medidas descrevem os três nomes observados, não uma largura máxima
universal. A matriz inclui à/À além dos acentos expressamente pedidos.
Não houve expansão de nomes padrão: suas reservas originais de 14 bytes
continuam preservadas.

O percurso passou pelo tutorial do save point, primeira batalha, obtenção da
carta de mapa e síntese de uma sala. Isso libera o menu Start de campo; só
abrir o primeiro mundo não satisfaz a guarda de tutorial da versão original.
Após Rename dos três baralhos, a interface do jogo confirmou Quick Save.

A exploração usou checkpoints privados para reduzir repetições. A prova final
reexecutou o trace completo desde reset, com o save normal de entrada, por
**26.830 frames**, sem checkpoint. SRAM e framebuffer finais coincidiram com
os da exploração. Depois, três processos novos carregaram esse Quick Save
com a ROM original, abriram Review Decks e selecionaram cada baralho. Os nomes
permaneceram acentuados. O consumo do Quick Save ao continuar é comportamento
do jogo; os arquivos de entrada não foram sobrescritos.

| Artefato | SHA-256 |
|---|---|
| ROM original | `6f6e7b61bb7b6ef7e2bea6e9dd01e70570a715835cc3713abe86186fd2c4e28d` |
| Candidata privada de teclado | `bb6ac542091b2f07b4e7d55bf7ab0e29f9a0447aec2534d81ecaa186ace2b683` |
| Save normal de entrada, preservado | `343914b33160032a7e05175d103348f15854c83f1154b3dbfcd7ecf513639c4a` |
| Quick Save produzido pelo jogo | `76eb99d03cea2723217f8124045c5a7179006b4f8ac6c246d7dbb3d0c632647f` |

Capturas principais:

- `private/runtime/menu-name1-ninth-rejected/frame-220.png`: rejeição do nono caractere.
- `private/runtime/menu-all-accents-selected{1,2,3}/`: os três estados de seleção antes de salvar.
- `private/runtime/menu-save-from-reset/frame-26830.png`: confirmação de Quick Save no replay integral.
- `private/runtime/menu-reload-names-1/frame-3600.png`,
  `menu-reload-names-2/frame-3900.png` e `menu-reload-names-3/frame-4200.png`,
  sob `private/runtime/`: os nomes após retomar com a ROM original.

## Comparação de pixels e limites restantes

`private/menu-probe/verify_pixels.py` compôs os nomes a partir do atlas latino
verificado, das larguras da ROM e das posições derivadas da fonte. As paletas
foram obtidas de nomes ASCII da ROM original. Foram comparadas 22 ocorrências:
os três nomes nas três seleções antes de salvar, as nove ocorrências equivalentes
após retomar, três telas Rename e a rejeição do nono caractere.

**20/22 ocorrências coincidem integralmente** nos pixels de tinta, sem pixels
extras das cores da fonte dentro de seus limites. Nas duas restantes, a mão
de seleção cobre seis e dois pixels do corpo/sombra do primeiro `Ú`, quando
o terceiro baralho está selecionado. A mão também cobre parte do `D` original
em outra captura. Isso permanece registrado como oclusão; não foi transformado
em aprovação de um nome completamente desobstruído. Os pixels que distinguem
cada forma acentuada de sua letra base coincidem em **todas as 22 ocorrências**.
O relatório conserva as divergências, coordenadas e RGB observados.

Esta prova não fecha o teclado PT-BR, nomes arbitrários, persistência dos nomes
acentuados em um slot normal, Riku, outros menus, fonte compacta, diálogos,
créditos ou texto em gráficos. Não demonstra ausência de inglês na tela.
As tarefas gerais de cobertura, fontes e QA de localização continuam abertas.
A execução ocorreu em macOS arm64 com o harness libmgba; não é QA do aplicativo
final, de áudio reproduzido, Windows ou hardware Intel.
