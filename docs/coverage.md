# Cobertura por recurso e ocorrência

`tools/coverage.py` calcula o gate de cobertura a partir do inventário completo
conhecido e de recibos de revisão ligados a IDs e digests. A presença de uma
tradução ou a quantidade de strings não libera a declaração de 100%.

```sh
.venv/bin/python tools/coverage.py inventory --rom "/caminho/sua-copia.zip" \
  --out private/coverage/inventory.json
.venv/bin/python tools/coverage.py check --rom "/caminho/sua-copia.zip" \
  --inventory private/coverage/inventory.json --ledger private/coverage/ledger.json \
  --evidence-root private/coverage --out private/coverage/report.json
```

Cada saída deve ser nova. A verificação retorna 0 quando o contrato de cobertura
está completo, 2 quando há pendências e 1 para entrada inválida. `check` extrai
novamente os proprietários de texto e recursos da ROM e impede removê-los ou
alterar seus spans/hashes no inventário editável. Descobertas adicionais exigem
intervalos e SHA-256 correspondentes aos bytes da origem. Ocorrências de uso
recebem IDs próprios, superfície e registro explícito de inventário fechado.

O ledger versão 1 contém `inventory_sha256`, `source_sha256`, `target_sha256`,
`patch_sha256`, `build_sha256`, `items`, `surfaces` e `receipts`. O digest do
inventário usa JSON UTF-8 canônico, com chaves ordenadas e sem espaços opcionais.
Cada item precisa de classificação e evidência: `visible_text`, `non_text` ou
`unreachable`. Recursos ainda desconhecidos bloqueiam o gate. Textos extraídos
não podem ser reclassificados simplesmente como `non_text`.

Um texto visível precisa de digest da tradução, revisão linguística, validação
binária e todas as ocorrências visuais. Texto igual à origem exige exceção por
item (`proper_name`, `brand` ou `title`), justificativa e recibo próprio. Um nome
aprovado não dispensa revisão de sua composição na tela. Os doze grupos do
design — incluindo Sora, Riku, vídeos, textos de link, variantes de fonte e UI
do aplicativo/instalador — precisam de revisão específica.

`receipts` mapeia IDs para `{ "path": "relativo.json", "sha256": "..." }`.
Cada JSON contém `schema_version: 1`, `kind`, `subject_id`, `source_sha256`,
`target_sha256`, `build_sha256`, `result: "pass"`, `reviewer` e `method`.
Recibos linguísticos, binários e visuais incluem `translation_sha256`.
O produtor de QA deve escrever esses recibos somente depois da verificação
correspondente e registrar em `method` os artefatos e o procedimento utilizados.
Eles são declarações rastreáveis do produtor: este gate confere integridade,
escopo e presença, sem se passar por revisão humana de imagem/prosa.

Recibos fora da raiz escolhida, arquivos ausentes/adulterados, revisão de outro
build/destino/tradução e escopo incompatível não contam como aprovação.
Orçamentos: 50 mil itens, 100 mil ocorrências/recibos, 1 MiB por recibo e
64 MiB de leitura agregada. O relatório traz denominadores por tipo, domínio
e superfície, além de contagens de classificação e pendências por ID.

## Resultado local

`private/coverage-v1/inventory.json` contém **18.083 itens**: **6.736 textos**
e **11.347 recursos**. Esses recursos ainda precisam de classificação semântica;
o número não significa 11.347 imagens com texto. A descoberta permanece aberta.
O ledger inicial não inventa aprovações a partir dos pilotos existentes:
`private/coverage-v1/report.json` registra cobertura incompleta e as pendências.

Nove testes com fixtures próprias verificaram aprovação sintética completa,
reabertura por item/ocorrência nova, superfície ausente, descoberta aberta,
recibo ausente/adulterado/de outro destino, tradução alterada, exceção nominativa,
inventário vazio/duplicado, retirada de proprietário, spans falsos e escape da
raiz de evidência. Aprovação sintética não é aprovação da ROM comercial.

A geração real do inventário, com dependências em cache, mediu 3,36 s de parede,
3,28 s de CPU usuário, 0,06 s de sistema e RSS máximo de 267.567.104 bytes.
Não lançou processos filhos. Custos de tokens e comparação cold/warm não foram
medidos. `coverage_complete` nunca substitui assinatura, composição de licenças,
testes de plataforma ou revisão final do proprietário; `release_approved`
permanece falso neste relatório.
