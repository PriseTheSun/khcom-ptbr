# Pipeline de localização: estado verificável

Esta etapa implementa inventário textual e edição de catálogos. **Não produz
tradução jogável nem comprova cobertura integral.** A reinserção disponível
recodifica textos sem edição e conserva os demais bytes; alterações editoriais
são bloqueadas enquanto faltarem fontes, métricas, caixas e referências
validadas. Não existe flag para ignorar essas verificações. A exceção experimental
é uma única fala fixa em `probe_dialogue.py`, descrita em [fonts.md](fonts.md),
que produz candidata privada para validação em runtime, sem aprovação de release.

## Fontes e propriedade dos formatos

`manifests/upstream.json` fixa fontes oficiais de
[Pheenoh/khcom](https://github.com/Pheenoh/khcom/tree/5dc49b75068bfe24e07bdaf365570d64682680c3),
commit `5dc49b75068bfe24e07bdaf365570d64682680c3`, com tamanho e SHA-256 por
arquivo. Inclui 12 manifests de pools, charmap US, `textgen.py`, `configure.py`,
README e licença CC0-1.0, além dos parsers/manifests/fontes do spike de fontes
documentado em [fonts.md](fonts.md). A licença do código não licencia os assets do jogo.

O snapshot fica em `.deps/khcom/`, ignorado. Os parsers de `textgen.py` são os
donos da interpretação dos manifests, alinhamento, terminadores e codecs.
Carregamos apenas os bytes verificados do módulo, sem reaproveitar `.pyc`
externo e sem executar seus comandos de geração. `configure.py` é lido por AST
para obter a identidade literal da ROM; ele não é executado. A verificação de
hash precede cada carregamento. Arquivos existentes divergentes são preservados
e causam falha; downloads somente acontecem com `--fetch-upstream`.

As ferramentas de extração/reinserção usam `read_rom` para admitir a ROM ou
membro ZIP selecionado. A revisão inicial é B8CE USA, SHA-256
`6f6e7b61bb7b6ef7e2bea6e9dd01e70570a715835cc3713abe86186fd2c4e28d`.
Não há aquisição de ROM nem execução do jogo nessas ferramentas.

## Uso local

Requer Python compatível com `pyproject.toml` e PyYAML 6.0.3 em ambiente virtual.
Os comandos abaixo são executados na raiz deste subprojeto. Cada saída deve ser
nova; arquivos existentes nunca são sobrescritos. Se repetir uma execução,
escolha outro nome de saída.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-tools.txt

# Pode preparar os formatos sem qualquer ROM, inclusive na CI pública.
.venv/bin/python tools/export_tables.py --fetch-upstream --out private/tables-us

.venv/bin/python tools/extract_text.py \
  --rom private/rom/B8CE.gba --out private/localization/catalog-us.json

.venv/bin/python tools/catalog.py export-csv \
  --catalog private/localization/catalog-us.json \
  --out private/localization/catalog-us.csv

.venv/bin/python tools/catalog.py import-csv \
  --catalog private/localization/catalog-us.json \
  --csv private/localization/catalog-us.csv \
  --out private/localization/catalog-us-imported.json

.venv/bin/python tools/reinsert.py \
  --rom private/rom/B8CE.gba \
  --catalog private/localization/catalog-us-imported.json \
  --out private/rom/B8CE-roundtrip.gba \
  --report private/reports/text-roundtrip.json
```

`--rom` também aceita ZIP e `--member` seleciona um membro exato quando
necessário. `--fetch-upstream` está disponível em extração, reinserção e
exportação de tabelas. JSON de diagnóstico não reproduz o texto do jogo.
Catálogos, CSV, ROM derivada e relatórios detalhados devem ficar em `private/`;
o programa rejeita destinos fora dela, inclusive escapes por symlink.
Não publicar esses arquivos.

## Contrato editorial

O catálogo mantém identidade estável `us/<pool>/<símbolo>`, domínio, codec,
intervalo em bytes, endereço GBA, hash do texto, reserva original, aliases
declarados, controles e fonte de proveniência. `pointer_refs`, contexto,
campanha, fonte, caixa e limites visuais permanecem `null` com explicação onde
não foram estabelecidos. Um nome de símbolo não prova campanha ou contexto.

`byte_budget` é a reserva original verificada; não representa espaço livre nem
autorização para ampliar texto. O registro preserva os comandos decodificados
do upstream e marca qualquer escape não interpretado como `opaque_code`.

O CSV inclui `id`, `source_text`, `translation`, `has_translation` e
`metadata_json`. Edite somente `translation` e `has_translation`: `1` indica
tradução presente, inclusive string vazia; `0` indica que ainda não existe
tradução e exige campo vazio. A distinção evita confundir vazio e `null`.
Ordem de linhas pode mudar; IDs duplicados, extras ou ausentes, origem
modificada e metadados adulterados são rejeitados.

Importação preserva a origem e normaliza somente a entrada editorial para NFC.
`translation_input` retém a entrada antes da normalização. Alterar uma tradução
invalida revisão/evidências anteriores e retorna o item a `draft`. Importar um
CSV não é aprovação de encoding, texto, fonte ou layout. Uma tradução editada
ainda não pode ser reinserida por esta etapa do pipeline.

JSON/CSV aceitam somente arquivos regulares, lidos com detecção de mudança,
até 64 MiB. O limite de 16.384 itens e de 128 Ki caracteres por campo textual
é um orçamento de edição, não um limite inferido do jogo. O catálogo real
inicial possui 6.736 itens, 14,3 MB em JSON e 9,5 MB em CSV. Cabeçalhos CSV
malformados/grandes retornam erro estruturado; FIFO não aguarda um escritor.

## Tabelas e renderização

São geradas `game-us.tbl`, `sjis-us.tbl` e `jp-us.tbl`. As chaves são
**sequências de bytes na ordem do arquivo**, em hexadecimal; a direita está o
caractere Unicode ou token de controle. Por exemplo `E100=á`, `0A00={NL}` e
`7940={HIGHLIGHT}` pertencem a `game`; não são UTF-8 na ROM.

O domínio `game` possui unidades little-endian de 16 bits e repertório CP1252
mais símbolos. Os domínios CP932 são de largura variável, embora o manifesto
declare a unidade mínima como um byte. Em `jp`, a sequência `6E6E` é controle
de nova linha; consumidores precisam dar prioridade aos controles/matches
mais longos. O CSV conserva o texto decodificado pelo parser, não usa uma
interpretação independente das tabelas.

As tabelas são exportações dos codecs, não substituem os parsers. Não há
`small-font.tbl`: o mapeamento da fonte pequena ainda não foi validado. O fato
de CP1252 conseguir codificar um acento não comprova sua presença gráfica.
A fonte latina já tem um spike separado de atlas/métricas e acentos observados
na ROM, detalhado em [fonts.md](fonts.md). Isso não atribui automaticamente a
mesma fonte/caixa a todos os itens; referências e realocação continuam abertas.

## Validação realizada

Executado localmente com Python 3.12.14/PyYAML 6.0.3 em macOS arm64:

| Pool examinado | Itens US recodificados |
|---|---:|
| card_description_text | 136 |
| card_help_text | 171 |
| card_message_text | 181 |
| common_text | 337 |
| event_name_text | 195 |
| event_text | 2.899 |
| jiminy_text | 2.501 |
| localized_names | 0 — não declara unidades US |
| movie_subtitle_text | 28 |
| msg_localized_text | 0 — não declara unidades US |
| staff_roll_script_text | 255 |
| ui_text | 33 |
| **Total** | **6.736** |

Os 12 manifests foram examinados; 10 possuem unidades US. Não houve divergência
do parser nem escape opaco nos itens extraídos. Codecs: `game` 6.248, `sjis`
471 e `jp` 17. Os intervalos/reservas verificados totalizam 431.836 bytes;
os textos efetivamente recodificados ocupam 431.629 bytes. Padding, intervalos
não textuais e dados restantes foram preservados, não declarados interpretados.

A ROM reconstruída sem edição ficou byte a byte idêntica, com o mesmo SHA-256
acima. JSON → CSV → JSON preservou todos os 6.736 itens e metadados. Nenhuma
tradução foi aplicada e nenhum jogo foi executado por esta validação.

Testes sintéticos cobrem endian/controles, CP932, códigos desconhecidos,
terminador ausente, intervalos sobrepostos, origem/span adulterados, membros
faltantes, bloqueio de reinserção editada, tabelas, CSV multiline/aspas/NFC,
IDs e metadados, escrita exclusiva e escapes por symlink:

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_text.py' -v
.venv/bin/python -m unittest discover -s tests -p 'test_catalog.py' -v
```

Uma medição do fluxo completo em processo Python novo, **filesystem já quente**,
incluiu extração, recodificação integral, exportação/importação CSV e comparação
dos catálogos gravados: 1,684 s de parede, 1,659 s de CPU e pico de 306.561.024
bytes de memória. Não houve processos filhos; portanto o pico da família
coincide com o processo. Não foram medidos cache frio de disco, custo de
aquisição upstream, Windows/Intel, tokens de tradução nem comparação com uma
implementação anterior. É uma amostra local, não orçamento universal.

## Limites abertos

- Os manifestos são inventário inicial, não uma prova de cobertura total.
- Fontes, glifos, caixas, controles dinâmicos, referências e contextos ainda
  exigem verificação em seus produtores/consumidores e no jogo.
- Gráficos/vídeos e texto fora desses pools não são extraídos por esta etapa.
- A ROM já tem 32 MiB; não é permitido assumir espaço livre nem anexar dados.
- Tradução contextual, reinserção editada, realocação, QA visual e campanhas
  permanecem pendentes. Passar no round-trip não fecha esses marcos.
