# Piloto privado de acentos nos créditos US

A candidata V2 executou as duas variantes de créditos pelo inicializador real e exibiu as 24 formas `á é í ó ú â ê ô ã õ ç à Á É Í Ó Ú Â Ê Ô Ã Õ Ç À` nas duas fontes. A comparação dos pixels nativos confirmou **96 ocorrências de glifos, 5.984 pixels e zero diferenças** nas quatro linhas capturadas de Sora e Riku. É um experimento privado, sem tradução dos créditos ou aprovação de tipografia final. Posteriormente, a receita foi incorporada à ferramenta de preparação descrita em [credits-profile.md](credits-profile.md), com equivalência binária comprovada; os auxiliares e resultados históricos deste piloto foram preservados.

## Identidade e alterações delimitadas

| Artefato | SHA-256 |
|---|---|
| ROM US original de 32 MiB | `6f6e7b61bb7b6ef7e2bea6e9dd01e70570a715835cc3713abe86186fd2c4e28d` |
| Candidata V2 | `dfff8d06c64071155a7cfa278d6df8112dcd17e3db53902ed91a7d6b04922f52` |
| BPS V2, 1.509 bytes | `7b49b0dcbcb3c8d38bb3fbc4bab29c79ac644256b053640b36c8db09dcb8b5f5` |
| Biblioteca estática usada nos ensaios | `82c5932f54a03219b835775255a6228d53947d38492b4031438737c63c8b06be` |

O construtor revalida a identidade original, tabelas, ponteiros e hashes das 631 linhas do ledger, auditoria estática dos consumidores e o ensaio original das duas variantes. Reutiliza exclusivamente os índices **210–233**, em quatro regiões de fontes/larguras que totalizam no máximo 1.200 bytes. Essas células contêm caracteres japoneses na origem; não são espaço vazio. A justificativa delimitada está em [credits-consumers.md](credits-consumers.md) e na comparação dinâmica do roteiro US em [credits-mode-entry.md](credits-mode-entry.md).

| Região | Endereços GBA, fim exclusivo | Bytes permitidos |
|---|---|---:|
| Pixels da fonte 0, 8×16 | `0x09A56740–0x09A56A40` | 768 |
| Pixels da fonte 1, 8×8 | `0x09A59BA0–0x09A59D20` | 384 |
| Avanços da fonte 0 | `0x09A545D2–0x09A545EA` | 24 |
| Avanços da fonte 1 | `0x09A547DE–0x09A547F6` | 24 |

As linhas 4 e 24 usam a fonte 0; 156 e 157 usam a fonte 1. Cada uma recebe o rótulo explícito `TESTE 0 ` ou `TESTE 1 `, doze acentos e NUL: 33 bytes, dentro da reserva original comprovada. Minúsculas e maiúsculas ocupam linhas separadas. O restante de cada reserva após o novo terminador é preservado. As linhas são diagnósticas; a alteração temporária de registros de nomes não constitui sua tradução.

A candidata tem **1.169 bytes diferentes** da original, todos dentro dessas quatro regiões e das quatro linhas, que permitem mais 132 bytes. Páginas, mapeamentos, ponteiros, outros índices, ícones e código do renderer permanecem idênticos. O perfil experimental interpreta `82A0..82B7` como os acentos; ele não redefine CP932 no catálogo geral. A reaplicação do BPS sobre a original produziu bytes idênticos à candidata. A ROM original foi preservada e a candidata permaneceu imutável em arquivo e na memória de ambos os ensaios.

## Revisão das formas

V1 foi preservada em `private/reports/credits-pilot-v1/` e **rejeitada visualmente**: o til da fonte 0 parecia um degrau descendente ou um grave grosso. V2 usa uma onda de quatro colunas com duas inclinações (`0101/1010` de primeiro plano), mais reconhecível a 1× e 4×. Entre V1 e V2, só 20 bytes dos quatro glifos `ã õ Ã Õ` da fonte 0 mudaram.

A fonte 0 aproveita o espaço superior e preserva o corpo das bases; `í` substitui o ponto e a cedilha usa as duas linhas inferiores. Na fonte 1, maiúsculas são compactadas para cinco linhas de corpo, `í` substitui seu ponto, C/c sobem uma linha e a sombra inferior da cedilha é omitida para respeitar a célula de 8 pixels. `ã/õ` passam do avanço 4 para 5 nessa fonte, admitindo a onda e sua sombra. Nenhum pixel não vazio ultrapassa o avanço declarado; as 24 matrizes de cada fonte são distintas.

Esses compromissos continuam experimentais. A igualdade de pixels não prova conforto de leitura a 1×, consistência tipográfica final, ou funcionamento em todas as posições da rolagem. Atlas e capturas permanecem privados, derivados da ROM fornecida pelo usuário.

## O que foi observado

Cada variante percorreu as linhas **0–626**, com **388 desenhos, 15.853 chamadas de glifo, cinco seleções de fonte e 16.875 eventos**, sem perda de trace. Todos os desenhos correspondem ao ledger da candidata em bytes, fonte, X, Y e ponteiro; os **384 desenhos não editados** permanecem iguais ao baseline original. Os 24 índices novos foram efetivamente consumidos em cada fonte. As linhas 627–630 são espaçadores finais não alcançados antes do fim da música; não se declara cobertura dinâmica das 631 linhas.

A entrada usa as mesmas três escritas de RAM declaradas e verificadas do diagnóstico original: flags de campanha `0x02039BB8`, argumento de modo `0x03007498` e modo pendente `0x03007494`. O fluxo real Title → Movie → StaffRoll é observado; não há injeção de PC, gravação de save no host ou comprovação de conclusão normal das campanhas. O helper privado não modifica `core/`, `app/` ou o runtime público.

A comparação de pixels usa o atlas decodificado da candidata, X e avanços do ledger e a paleta original `gStaffRollTextPalette` em `0x09D6BE14`. O renderer seleciona índices de paleta `0/15/13/14`, convertidos pelo mGBA em RGB preto, branco, cinza 24 e cinza 99. O Y de cada captura é **medido**, por correspondência exata e única do rótulo ASCII preservado: Y=81 em todas as oito imagens. Depois se comparam todos os pixels dentro do avanço de cada acento, sem ajuste por glifo, tolerância, máscara de exclusão ou redimensionamento. Nenhuma diferença ou oclusão foi encontrada nesses retângulos, todos dentro da janela dos créditos. Outras posições e sobreposições de sprites não foram verificadas.

O contrato exige as quatro edições exatas, oito pares únicos variante/linha, doze glifos por linha, as 24 letras por fonte/variante e 96 ocorrências no total. Doze casos negativos com listas vazias/parciais/duplicadas, letra/índice/fonte incorretos e variante ausente foram rejeitados, usando cópias dos relatórios reais. Uma lista vazia não pode sustentar a conclusão de cobertura.

## Evidência e reprodução local

Todos os caminhos abaixo são relativos a `projects/khcom-ptbr`. Os scripts são auxiliares privados desta experiência; a versão pública não inclui ROM, BPS, glifos, atlas nem esses helpers. Requer a própria ROM validada, dependências locais já verificadas, fontes upstream do commit fixado e os ledgers/relatórios prévios preservados.

Os relatórios consolidados ficam em `private/reports/credits-pilot-v2/`:

- `evidence.json`: identidade, escopo, medidas e hashes dos artefatos/fontes auxiliares.
- `build-report.json` e `bps-report.json`: regiões permitidas, bases, receita, limites e reaplicação. O relatório de construção registra o estado anterior à execução; a confirmação posterior está nos relatórios abaixo.
- `candidate-ledger.json` e `verification.json`: comparações de texto e execução.
- `pixel-verification.json` e `pixel-contract-checks.json`: 96 ocorrências/5.984 pixels e testes negativos da cobertura.
- `font{0,1}-matrix-{native,4x}.png`: atlas de revisão, com matrizes e metadados adjacentes.
- `run-{sora,riku}/row-{4,24,156,157}.png`: capturas nativas das quatro linhas; `.rgb` é a captura bruta. Traces JSONL, resumo e relatório ficam no mesmo diretório.

Comandos executados, com o diretório do projeto como diretório atual:

```sh
.venv/bin/python private/reports/credits-pilot-v2/build_pilot.py
clang++ -O2 -std=c++20 -mmacosx-version-min=13.0 \
  -I. -Ibuild/_deps/mgba-src/include -Ibuild/_deps/mgba-build/include \
  private/reports/credits-pilot-v2/trace-pilot.cpp core/sha256.cpp \
  private/reports/credits-pilot-v1/libmgba.a -framework CoreFoundation \
  -o private/reports/credits-pilot-v2/trace-pilot
/usr/bin/time -l private/reports/credits-pilot-v2/trace-pilot \
  private/reports/credits-pilot-v2/candidate.gba \
  private/reports/credits-pilot-v2/run-sora sora \
  > private/reports/credits-pilot-v2/run-sora.stdout.log \
  2> private/reports/credits-pilot-v2/run-sora.stderr.log
/usr/bin/time -l private/reports/credits-pilot-v2/trace-pilot \
  private/reports/credits-pilot-v2/candidate.gba \
  private/reports/credits-pilot-v2/run-riku riku \
  > private/reports/credits-pilot-v2/run-riku.stdout.log \
  2> private/reports/credits-pilot-v2/run-riku.stderr.log
.venv/bin/python private/reports/credits-pilot-v2/verify-pilot.py
.venv/bin/python private/reports/credits-pilot-v2/verify-pixels.py
.venv/bin/python private/reports/credits-pilot-v2/test-pixel-contract.py
```

Os diretórios `run-*` devem ser novos: o helper rejeita sobrescrita. Para repetir a execução, crie uma nova revisão privada e ajuste os caminhos fixos dos auxiliares, preservando a evidência anterior. A reaplicação/verificação dos relatórios existentes pode ser repetida sem executar a ROM. O helper fixa o SHA da candidata; outra ROM é rejeitada.

A biblioteca foi copiada antes da correção independente da geração de versão do mGBA. Os relatórios retêm seu identificador bruto antigo `0.10-main-1-6c7971b-dirty`; a identidade do binário efetivamente usado está fixada pelo SHA acima, sem reatribuir a execução ao rebuild posterior.

Com dependências em cache e os dois processos lançados simultaneamente, `/usr/bin/time -l` mediu Sora em 9,74 s (CPU 9,23 s usuário + 0,05 s sistema) e Riku em 9,51 s (9,01 + 0,05 s). Cada processo atingiu 75.087.872 bytes de RSS máximo; os helpers não criaram processos filhos. O pico agregado simultâneo e a contagem de tokens não foram medidos. Não houve nova bateria pública de CTest: as mudanças desta etapa são documentação e auxiliares privados, verificados pelos ensaios acima.

Este piloto não fecha as tarefas gerais 2.5, 2.6 ou 2.14: outros renderizadores, cenas, texto gráfico e a tradução completa continuam pendentes. O BPS privado contém derivados de bases gráficas fornecidas pelo usuário; sua distribuição não foi aprovada.
