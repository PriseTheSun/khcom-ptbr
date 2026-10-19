# CI de fontes, builds e QA privado

Os workflows estão na raiz do repositório do jogo, em `.github/workflows/`.
O remoto é `PriseTheSun/khcom-ptbr`; o REA não recebe esses jobs.

## Execuções observadas

No commit `a4ca832464e59f5096dc3447cfbd147aaa966c15`, o run público
[39180402142](https://github.com/PriseTheSun/khcom-ptbr/actions/runs/39180402142)
passou nos testes de fontes. O run desktop
[39180402200](https://github.com/PriseTheSun/khcom-ptbr/actions/runs/39180402200)
falhou nos três runners durante setup-python: Python 3.12.14 não tem os artefatos
Windows/macOS solicitados. O log Windows confirma a ausência do x64; o manifesto
oficial python-versions confirma que 3.12.10 oferece as três combinações usadas.
O workflow desktop foi corrigido para **3.12.10**. Python é ferramenta de build,
não dependência do executável. A execução Ubuntu mantém 3.12.14, que passou.

Esses resultados pertencem ao commit antigo. A implementação local nova só
pode ser chamada de CI verificada depois de seu próprio run. Relatórios com
identidade e logs relevantes permanecem em `private/reports/github-ci-v1.json`.

## Workflows

- `ci.yml`: parsers fixados, Floating IPS independente, testes Python com
  fixtures próprias e staging sem jogo comercial.
- `desktop-build.yml`: CMake/CTest Windows x64, macOS arm64 e macOS x86_64,
  empacotamento com fontes/licenças/SBOM, instalador Inno Setup por usuário e
  montagem de `.app` universal a partir das duas slices. Artefatos são previews
  experimentais, não releases assinadas nem tradução completa.
- `private-game-qa.yml`: somente `workflow_dispatch` em `main` no repositório
  esperado, ambiente protegido `private-game-qa` e runner com label dedicado
  `khcom-private-ephemeral`. Faz smoke de 180 frames com a ROM/pacote fornecidos
  localmente pelo proprietário. Só JSON de campos permitidos é enviado; dumps,
  saves, imagens e logs detalhados ficam no armazenamento privado do runner.
- `release.yml`: valida origem/commit/run privado e exige o contrato completo
  de `validate_release.py`. O smoke atual não produz um `release-candidate`;
  assinatura, QA completo, aprovação humana e publicação permanecem abertos.

Configure o runner privado como descartável e exclusivo dessa rotina, com
`KHCOM_QA_ROM`, `KHCOM_QA_PACKAGE` e `KHCOM_PRIVATE_QA_DIR` no ambiente preparado
pelo proprietário. A pasta privada deve existir fora do checkout. Não use esse
runner para PRs públicos. O workflow não instala ferramenta global nem transfere
ROM por secret/artefato. A existência do YAML não significa que o runner ou as
proteções do ambiente estejam provisionados.

As actions estão fixadas por commit. PyYAML, pyelftools, CMake e Ninja têm versões
com hashes; as dependências C++ têm arquivos/hash fixados. O instalador exige
Inno Setup 6.7.1 já presente na imagem Windows, em vez de baixar uma versão
flutuante. Labels de runner fixam a família, não uma imagem imutável: SDK e
compilador precisam permanecer registrados nos logs e no manifesto final.

Os jobs públicos usam `contents: read`, checkout sem retenção de credencial e
runners hospedados efêmeros. Não há `pull_request_target`, cache de dados privados
ou secrets de assinatura. O upload é restrito aos caminhos de saída do
empacotador auditado. O job universal reaudita os pacotes de entrada e exige
fontes correspondentes iguais antes de combinar as slices.

## Verificação local

Actionlint 1.7.12 validou os quatro workflows, com o label privado declarado em
`.github/actionlint.yaml`. A suite Python executou 135 testes, sem skips, no
registro `private/reports/python-tests-v9.log`; isso é o snapshot dessa execução,
não um substituto para os testes posteriores a novas alterações.

O smoke privado foi executado localmente com V2: 180 frames, origem preservada,
SHA de destino correto, relatório sanitizado sem caminhos de ROM/save/captura.
Usou dispositivos SDL dummy, portanto não comprova áudio físico nem QA completo.
A execução no runner privado GitHub continua indisponível até provisionamento.

`distribution.md` explica o empacotamento e os gates. As provas anteriores do
harness universal via Rosetta ficam em `core-version.md`; não comprovam Mac
Intel físico nem substituem o teste do aplicativo novo.
