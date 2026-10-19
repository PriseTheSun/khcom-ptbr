# Identidade do core no build

O arquivo de dependências fixa o arquivo-fonte mGBA 0.10.5 por SHA-256.
Entretanto, o gerador `mgba-version-info` invocava `version.cmake` em outro
processo CMake sem transmitir `SKIP_GIT`. Dentro deste repositório, esse
processo encontrava o Git do jogo e gerava `0.10-main-1-6c7971b-dirty`.
Esse identificador descrevia o checkout pai, não uma revisão do emulador.

`cmake/PatchMgbaVersion.cmake` corrige a regra na árvore extraída, passando
`-DSKIP_GIT=ON`. Na etapa de população/aplicação do patch, o arquivo original
precisa ter o SHA-256 esperado; uma repetição dessa etapa aceita apenas o
resultado exato do patch. Alterações inesperadas interrompem essa aplicação.
Essa guarda não é uma auditoria contínua de toda a árvore extraída durante
rebuilds que reutilizem o cache. O arquivo compactado original permanece intacto, e os fontes de
emulação não mudam. O aviso de dependências registra essa modificação de build.

O contrato C++ confere a versão efetivamente exportada pela biblioteca contra
o manifesto fixado. Isso cobre os dois processos de geração e detecta a
regressão observada dentro de um checkout Git. A versão passou a ser `0.10.5`,
com commit/branch desconhecidos, pois a entrada é um arquivo de release.
A identidade forte continua sendo o hash do arquivo-fonte e do binário.

Após a correção, CTest passou 2/2 nativamente em arm64 e 2/2 via Rosetta em
x86_64. Uma execução da ROM original por 1.440 frames teve exatamente os
mesmos hashes de framebuffer e save, contadores de áudio e logs da execução
anterior. Logs e hashes estão em `private/reports/core-version-*` e
`private/reports/universal-diagnostic-v4.json`. O resultado não certifica
Windows, Intel físico ou os requisitos finais de distribuição.

Os relatórios anteriores preservam a versão crua realmente observada.
O executável/lib arm64 anterior foi retido em
`private/toolchain/before-core-version-fix/`; o universal anterior permanece
em `build-universal-v3/`. Evidências históricas não foram reatribuídas ao build
novo. Checkpoints diagnósticos vinculados à versão antiga são rejeitados pelo
novo build, conforme o contrato existente. Saves de cartucho não usam esse
cabeçalho e não são migrados ou sobrescritos por esta alteração.
