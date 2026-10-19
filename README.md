# Kingdom Hearts: Chain of Memories — projeto PT-BR

Subprojeto independente do REA, orientado pela mudança OpenSpec
`khcom-ptbr-desktop`. Prioridade: campanhas Sora e Riku. Multiplayer funcional
fica para uma fase posterior; seus textos continuam no escopo da tradução.

**Estado: ferramentas de investigação e executável de diagnóstico. Ainda não
é o jogo traduzido nem um pacote de distribuição.** O relatório de implementação
em `docs/implementation.md` separa resultados executados e pendências.

## O que já pode ser usado

- Identificação por conteúdo da ROM USA B8CE, inclusive ZIP com seleção explícita.
- Extração dos pools conhecidos para JSON/CSV UTF-8 e exportação de `.tbl`.
- Reinserção sem edição, comprovando igualdade integral com a ROM original.
- Criação/aplicação BPS com CRCs, SHA-256 e relatório dos literais a revisar.
- Harness nativo libmgba/SDL para frames, entrada reproduzível, capturas e saves.
- Prova experimental de uma fala em PT-BR, com acentos, executada e inspecionada.
- Piloto gráfico APERTE INICIAR, preservando os cinco quadros do aviso original.
- Prova dos 24 acentos em nomes de baralhos, com Quick Save e retomada.
- Auditoria do roteiro de créditos, fontes, códigos e limites de bytes/largura.
- Reconstrução local de acentos nas duas fontes de créditos, equivalente ao piloto Sora/Riku.
- Mapa conjunto de textos e 11.347 recursos, com referências desconhecidas explícitas.
- Extração e reconstrução idêntica de 4.900 recursos gráficos declarados.
- Diagnóstico de candidatos textuais por ID, com bloqueios explícitos de layout/referências.

As ferramentas não baixam ROM, BIOS da Nintendo, saves ou assets do jogo.
O usuário fornece a ROM. Nenhum arquivo original é incluído no código-fonte
preparado para revisão.

## Organização

| Pasta | Uso |
|---|---|
| `tools/`, `tests/` | Pipeline Python e testes com dados próprios |
| `app/`, `core/`, `platform/`, `cmake/` | Harness C++20 e integração do core |
| `manifests/` | Revisões, hashes e proveniência das dependências |
| `.github/workflows/` | CI de fontes e compilação do diagnóstico sem ROM |
| `docs/` | Contratos, comandos e resultados verificáveis |
| `private/` | ROM, catálogos, imagens, saves e resultados locais; ignorada |
| `.deps/`, `.venv/`, `.build-tools/`, `build/` | Dependências e builds locais; ignorados |
| `stage/` | Staging de fontes selecionadas, sem dados privados; ignorado |

O projeto não participa do pacote npm do REA. O staging de fontes usa uma lista
explícita de áreas/extensões e rejeita links simbólicos. Staging de executáveis,
auditoria de licenças para release e instaladores são tarefas posteriores.

## Começar

Execute os comandos nesta pasta. Use Python 3.11 ou superior; o ambiente local
verificado usa Python 3.12.14. Nenhuma instalação global é necessária.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-tools.txt

.venv/bin/python tools/identify_rom.py --input "/caminho/sua-copia.zip" \
  --copy-to private/rom/B8CE.gba --out private/reports/identity.json

.venv/bin/python tools/extract_text.py --fetch-upstream \
  --rom private/rom/B8CE.gba --out private/localization/catalog-us.json
```

No Windows, substitua `.venv/bin/python` por `.venv\Scripts\python.exe`.
As saídas devem ter nomes novos; os scripts preservam arquivos existentes.
`--member "pasta/nome.gba"` escolhe uma candidata de um ZIP com várias ROMs.

O SHA-256 aceito é
`6f6e7b61bb7b6ef7e2bea6e9dd01e70570a715835cc3713abe86186fd2c4e28d`.
Nome do arquivo não determina a revisão. ZIP64, volumes divididos e entradas
criptografadas não fazem parte do importador inicial; detalhes e limites estão
em `tools/khcom/rom.py`.

Leia [localização](docs/localization.md) para CSV, `.tbl` e round-trip;
[validação](docs/validation.md) para erros por ID e limites ainda desconhecidos;
[runtime](docs/runtime.md) para compilar e executar o diagnóstico;
[patches](docs/patches.md) para BPS e seu gate de distribuição;
[fontes](docs/fonts.md) para o probe de diálogo e os renderizadores pendentes;
[gráficos](docs/graphics.md) para extração sem perda de tiles, paletas e animações;
[piloto do título](docs/title-graphic-probe.md) e [baralhos](docs/menu-probe.md) para provas delimitadas;
[créditos](docs/credits.md) para a auditoria de roteiro e largura;
[perfil PT-BR dos créditos](docs/credits-profile.md) para reconstruir fontes e exportar sua tabela;
[mapa de recursos](docs/asset-map.md) para ocupação e referências pendentes.

## Verificação pública, sem ROM

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
.venv/bin/python tools/stage_sources.py --out stage/source-review
```

Os testes dos formatos upstream precisam do snapshot fixado, obtido com
`tools/export_tables.py --fetch-upstream --out private/tables-us`. Não precisam
da ROM comercial. O teste cruzado BPS usa Floating IPS somente quando seu
executável é indicado em `KHCOM_FLIPS`; o relatório deve informar se foi pulado.

## Critérios que continuam abertos

O inventário inicial não comprova 100% dos recursos do jogo. Faltam a tradução
contextual, suporte verificado a todas as fontes, edição gráfica/vídeos,
realocação, prova visual das duas campanhas e o aplicativo final. Um codec que
aceita `ã` não comprova que o renderer desenha esse glifo.

O diagnóstico possui um binário macOS com slices Intel/Apple Silicon; Intel foi
testado via Rosetta. Isso não é o `.app` final nem QA em hardware Intel.
Os [workflows de CI](docs/ci.md) foram validados estaticamente, sem execução remota.
Windows, assinatura/notarização, CI de distribuição e Android ainda não são
entregas verificadas. Consulte o checklist OpenSpec antes de
anunciar qualquer plataforma ou porcentagem de tradução concluída.
