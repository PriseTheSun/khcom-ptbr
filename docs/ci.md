# CI de fontes e diagnóstico

Os workflows estão em `.github/workflows/` **dentro do subprojeto**. O staging
preserva esse caminho para quando o projeto ocupar a raiz de seu próprio
repositório. Eles não foram instalados na CI do REA. Esta árvore local não tem
remoto do jogo selecionado; nenhuma execução GitHub foi iniciada.

## Workflows implementados

`ci.yml` obtém fontes de formato fixadas e verificadas, compila Floating IPS no
commit do manifesto, executa a suite Python com fixtures próprias e verifica
staging. Não carrega uma ROM comercial. `desktop-build.yml` compila o diagnóstico
e executa CTest em Windows x64/MSVC, macOS arm64 e macOS Intel. As arquiteturas
dos hosts são verificadas explicitamente antes do build.

As actions de checkout e Python estão fixadas por commit. A instalação Python
e CMake/Ninja usa versões fixadas; os wheels PyYAML/CMake/Ninja têm hashes.
mGBA/SDL vêm do manifesto existente, com verificação SHA-256 pelo CMake.
Os labels dos runners fixam a família do sistema, **não uma imagem imutável**;
os compiladores/SDK provisionados ainda variam e aparecem nos logs de configure.
Isso não é uma alegação de builds bit a bit reproduzíveis.

Os jobs usam runners hospedados efêmeros, `contents: read`, checkout sem retenção
de credencial, nenhum secret, cache ou upload. Executam PRs no contexto
`pull_request`; não usam `pull_request_target`. Binários de diagnóstico ficam
apenas no runner enquanto o pacote de licenças/fontes/relink não estiver pronto.
Não há publicação, instalador ou assinatura nessas rotinas.

Os SHAs foram resolvidos nos repositórios oficiais de
[checkout](https://github.com/actions/checkout/tree/3d3c42e5aac5ba805825da76410c181273ba90b1)
e [setup-python](https://github.com/actions/setup-python/tree/5fda3b95a4ea91299a34e894583c3862153e4b97).
Os labels de arquitetura foram conferidos na
[lista de imagens de runners](https://github.com/actions/runner-images).

## Verificação executada localmente

Actionlint 1.7.12 validou ambos os workflows. O binário local foi conferido contra
o checksum publicado do release; proveniência em
`private/reports/actionlint-tool.json`. ShellCheck e Pyflakes não foram
executados por essa chamada. Validação estática não substitui uma execução do
workflow, especialmente a primeira compilação Windows/MSVC.

O build macOS x86_64 terminou com AppleClang/SDK presentes na máquina arm64.
CTest passou 2/2 **via Rosetta**, registrado em
`private/reports/core-version-x86-ctest.log`. `lipo` produziu
`build-universal-v4/khcom-diagnostic`, contendo x86_64 e arm64, e `--help` passou
com seleção explícita de cada slice. O artefato é uma ferramenta CLI local,
sem bundle `.app`, assinatura Developer ID ou notarização. Isso não comprova
QA em um Mac Intel físico nem nas versões mínimas propostas do macOS.
`core-version.md` descreve a correção do gerador de versão da dependência e
os binários históricos preservados.

## Gates ainda abertos

As tarefas 6.1–6.11 permanecem abertas conforme seu checklist: execução real
da CI, frontend final, pacotes/instaladores, auditoria de composição por
plataforma, QA privado por digest, bundle universal completo, assinatura e
notarização, atualização e release reproduzível. A existência destes workflows
não fecha o marco de distribuição.
