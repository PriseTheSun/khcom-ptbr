# Empacotamento e limites de distribuição

`package_desktop.py` gera uma prévia desktop sem ROM, save, BIOS ou BPS. O macOS
recebe um bundle `.app`; o Windows recebe um executável em ZIP e a CI prepara
um instalador por usuário com Inno Setup. A origem de cada arquivo é selecionada
pelo empacotador; `audit_package.py` rejeita arquivos extras/ausentes, links,
dados de jogo conhecidos, identidades divergentes e material de fontes/licenças
ausente. A auditoria não transforma um pacote experimental em release final.

```sh
.venv/bin/python tools/package_desktop.py --binary build/khcom-desktop \
  --build build --platform macos --out dist/macos-new
.venv/bin/python tools/audit_package.py --package dist/macos-new/payload
```

O bundle macOS é selado **ad-hoc** para execução local. Isso não é assinatura
Developer ID nem notarização; nenhuma identidade Apple válida foi encontrada
na máquina. A verificação Mach-O exige slices declaradas, ausência de rpaths
e dependências apenas em `/usr/lib`/`/System/Library`. O app é ligado
estaticamente; não há outros Mach-O internos nessa composição. O mínimo macOS
13.0 é proposto pelo build, ainda não validado em uma máquina com esse sistema.

O ZIP inclui `corresponding-source.zip`, avisos completos, SBOM CycloneDX e
instruções de reconstrução. O pacote de fontes contém o snapshot autoral usado
e quatro arquivos upstream originais conferidos pelo manifesto. Para mGBA,
inclui as fontes correspondentes com inventário por arquivo, excluindo o
corpus `cinema/` que contém 162 ROMs de teste alheias ao core incorporado. A modificação
de build mGBA está em `cmake/PatchMgbaVersion.cmake`. As fontes e o build permitem
recompilar/religar com blip_buf modificado, conforme a alternativa de fontes da
[LGPL 2.1, seção 6](https://www.gnu.org/licenses/old-licenses/lgpl-2.1-standalone.html).
O SBOM registra também componentes incorporados, fonte UI e shader; as licenças
exatas permanecem nos avisos/fontes. Revisão de distribuição é um gate separado.

O instalador usa `PrivilegesRequired=lowest`, grava em LocalAppData/Programs e
não solicita administrador. Não há regra para apagar dados de usuário na
desinstalação. Saves/configuração são geridos pelo aplicativo fora do bundle
e da pasta de instalação. Instalação limpa, atualização, rollback e remoção
ainda exigem teste nativo dos pacotes finais; a configuração não prova execução.

## Patches e receita local

O BPS dos pilotos contém glifos e composições derivadas da ROM. Ele permanece
privado. `audit_patch.py` regenera o destino pelo produtor fixo, exige patch
idêntico sem metadados adicionais e atribui cada literal a um componente.
Texto traduzido e valores de referência são separados de composições derivadas
dos pixels originais. O relatório rejeita a distribuição pública desse BPS.

```sh
.venv/bin/python tools/audit_patch.py --rom CAMINHO_DA_ROM_OU_ZIP \
  --patch private/desktop-package-v2/translation.bps \
  --recipe-out private/new-recipe.json --report private/new-literal-audit.json
.venv/bin/python tools/reconstruct_recipe.py --rom CAMINHO_DA_ROM_OU_ZIP \
  --recipe private/new-recipe.json --out private/reconstructed-new
```

A receita JSON contém somente versão e hashes. O consumidor rejeita comandos,
payloads ou builders divergentes e usa código fixo, nunca `eval`/shell vindo da
receita. O usuário reconstrói os bytes derivados a partir da própria ROM. A
receita pública depende das ferramentas Python de edição; o desktop atualmente
aplica o BPS **já gerado localmente**. Integrar a receita à primeira execução
sem Python continua uma pendência distinta da prova de reconstrução.

## Gate de release

`validate_release.py` exige os três pacotes finais, digests e recibos ligados ao
mesmo commit, ROM, patch, inventário e conjunto de artefatos. Os gates incluem
as duas campanhas, cobertura, gráficos/vídeos/créditos, máquinas nativas,
desempenho, proveniência, atualização, reprodução, assinatura/notarização e
revisão humana. Os recibos devem vir do ambiente privado controlado pelo
proprietário; hashes comprovam integridade, não a verdade de uma declaração.

Os testes negativos executados rejeitam mudança de artefato, QA ausente,
assinatura ausente, revisão humana ausente, Rosetta apresentado como Intel
nativo, digest/commit divergente, caminho externo e candidato experimental.
O workflow `release.yml` confere a origem do run privado e apenas valida o
candidato. O smoke privado atual não produz um `release-candidate` completo;
publicação e credenciais continuam pendentes. Nenhum recibo humano foi criado
em nome do proprietário e nenhuma release completa foi publicada.
