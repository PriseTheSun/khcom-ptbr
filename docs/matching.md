# Baseline matching, ocupação e realocação interna

A reconstrução integral privada do upstream `Pheenoh/khcom` no commit
`5dc49b75068bfe24e07bdaf365570d64682680c3` reproduziu os **33.554.432 bytes** da
ROM USA B8CE rev0. Origem, `com_us.gba` e `verified.gba` têm SHA-256
`6f6e7b61bb7b6ef7e2bea6e9dd01e70570a715835cc3713abe86186fd2c4e28d`.
O build terminou os 604 passos, incluindo a comparação integral do upstream.
Os arquivos originais do usuário permaneceram intactos.

O ELF tem SHA-256
`6498bbaaed4b0e944def1ad55fc1e40a3d719b648f99e4f13f72d4167353e2ec`;
o mapa do linker tem SHA-256
`ed31aa2201de1705566d447ec6cf6bbf1e3fb0322d56972836f0090995c722f9`.
A evidência completa permanece em `private/matching-v1/baseline.json`,
`facts-v3.json` e nos logs de extração/configuração/build. Dados, objetos,
binários e imagens derivados do jogo permanecem privados.

## Produtor canônico de fatos

`tools/audit_matching.py` / `khcom.matching.audit_matching_bytes` fazem uma
leitura fresca da ROM, reconstrução, ELF, mapa GNU ld 2.10 e **524 objetos**.
O produtor usa pyelftools 0.32, fixado com hashes em `requirements-tools.txt`.
O adaptador de bytes preserva a identidade da entrada do chamador, inclusive
ROM selecionada em ZIP; não requer criar outra cópia temporária.

```sh
.venv/bin/python tools/audit_matching.py \
  --rom private/rom/B8CE.gba \
  --rebuild "$MATCHING_TREE/build/us/com_us.gba" \
  --elf "$MATCHING_TREE/build/us/com_us.elf" \
  --map "$MATCHING_TREE/build/us/com_us.map" \
  --source-root "$MATCHING_TREE" \
  --word 32483772 --out private/matching-new.json
```

O relatório `khcom-matching-facts-v1` vincula todos os inputs por SHA-256 e
retém seções, símbolos, ocupação, palavras selecionadas e **98.607 referências
`R_ARM_ABS32`**. Cada referência resolve símbolo, seção, addend e bit Thumb
legado; o valor calculado precisa corresponder à palavra da ROM. Os 31.907
`R_ARM_THM_CALL` e 26 `R_ARM_PC24` são decodificados e conferidos separadamente
no campo `direct_calls`, preservando addend e PC ARM/Thumb. Apenas BL Thumb
ARMv4T e B/BL ARM são admitidos; BLX não é assumido compatível. São desvios
diretos, sem tratá-los como ponteiros de dados. O ELF coincide com a ROM nos intervalos `[0,4)` e
`[192,32489436)`; o cabeçalho intermediário é corrigido pelo `gbafix`, e a cauda
restante é FF. A comparação do rebuild já cobre o arquivo inteiro.

Uma palavra com forma de ponteiro não é automaticamente uma referência.
Os seis valores que coincidiam com o interior de `gStaffRollAllStaffFansText`
pertencem a tiles 4bpp de `gRikuBt10Tiles`, `gNiserikuDamageTiles` e
`gCroudB02Tiles`. O valor no offset 28356440 pertence ao payload do bloco de
áudio 4611 em `gBlockAudioData`. `khcom.matching_assets` verifica hashes dos
manifestos/fontes fixados, limites, identidade integral dos recursos codificados
com a ROM e enquadramento do áudio antes de classificá-los como
`encoded_asset_data_verified`. Em contraste, o offset 32483772 é uma referência
real a `gStaffRollSpaceText`, no objeto local `sStaffRollSpaceText`: outro
consumidor que mede a largura do espaço. A classificação não autoriza editar
esse consumidor sem seu contrato.

| Memória | Reserva estática no ELF | Capacidade | Restante não atribuído |
|---|---:|---:|---:|
| IWRAM | 30.072 | 32.768 | 2.696 |
| EWRAM | 253.792 | 262.144 | 8.352 |

A reserva inclui heaps estáticos definidos pelo linker. O restante **não é
uma licença para alocar**: pico dinâmico de heap/pilha não foi medido. Gaps e
FF finais também não são declarados espaço livre. A auditoria de relocações
não substitui análise completa de endereços calculados em ARM/Thumb.

## Realocação demonstrada

O piloto usa somente a união original de três objetos consecutivos,
`[1416688,1416734)`, com 46 bytes. “Salvar jogo?” ocupa 26 bytes em vez de 32;
“Sim” ocupa 8; “Não” ocupa 8 em vez de 6; os 4 bytes restantes são padding
explícito. Os destinos novos são:

| Símbolo | Offset anterior | Offset novo | Bytes novos |
|---|---:|---:|---:|
| gMapSaveConfirmText | 1416688 | 1416688 | 26 |
| gYesChoiceText | 1416720 | 1416714 | 8 |
| gNoChoiceText | 1416728 | 1416722 | 8 |

Todas as 21 referências dos três objetos foram conferidas; 20 mudaram.
Uma busca em **todos os alinhamentos**, para cada endereço interior da união,
não encontrou palavras adicionais fora das referências do linker. Uma
recompilação independente da assembly do objeto e relink integral gerou bytes
idênticos ao escritor do piloto. Todos os símbolos fora desses três objetos
preservaram endereço e tamanho. Somente 40 bytes da ROM diferem, dentro da
união ou das palavras de referência; o tamanho continua 32 MiB. O teste
`test_growth_beyond_gba_cartridge_is_rejected` rejeita 32 MiB + 1 byte.

O SHA-256 do candidato é
`2dbd71ae676e745d7a9bdb9080fa23b682a0c7f3ca23b2b3f26b2e2cdacef54e`.
O patch BPS de 167 bytes reaplicado pelo leitor do projeto e pelo Flips produz
a mesma ROM. `private/relocation-v1/relink-proof.json` retém a diferença de
símbolos/bytes; `independent-bps.json` retém a verificação independente.

Para repetir a prova contra uma árvore matching fresca:

```sh
.venv/bin/python tools/probe_relocation.py --rom private/rom/B8CE.gba \
  --matching-tree "$MATCHING_TREE" --out private/relocation-new/candidate.gba
```

Para compor o pacote diagnóstico sem distribuir a toolchain, a API
`khcom.relocation_probe.build_verified_relocation_probe(original_bytes)`
reproduz a **receita congelada**. O contrato público
`manifests/relocation-menu-v1.json` contém apenas metadados, 21 referências,
três símbolos e hashes de proveniência. Seu próprio SHA-256, a origem e a
saída estão fixados no produtor. Isso não aceita uma nova tradução ou uma
realocação arbitrária; mudar a receita exige nova prova e versão.

O replay real de 78.700 frames desde reset em mGBA 0.10.5 mostrou
“Salvar jogo?”, “Sim” e “Não” no frame 78.000, sem sobreposição visível.
O save SRAM resultante e o framebuffer final são idênticos ao replay original.
A imagem está em `private/runtime/relocation-from-reset/frame-78000.png`;
o relatório e `private/relocation-v1/runtime-proof.json` preservam as condições.
O log contém os mesmos 65.414 eventos `game_error` do baseline, principalmente
I/O somente leitura/DMA; isso não foi apresentado como execução sem avisos.
A imagem ainda tem rótulos ingleses; não prova tradução completa. Outros
consumidores compartilhados de Sim/Não ainda precisam de QA visual.

## Toolchain privada e reprodução

Nenhum instalador global foi executado. Foram usados:

| Entrada | Revisão / identidade |
|---|---|
| khcom | commit `5dc49b75068bfe24e07bdaf365570d64682680c3` |
| Arm GNU Toolchain | 13.2.Rel1, Darwin arm64; arquivo SHA-256 `39c44f8af42695b7b871df42e346c09fee670ea8dfc11f17083e296ea2b0d279` |
| agbcc | commit `da598c1d918402c42c0c0d7128ba14567f3175e9`; arquivo SHA-256 `f69ae187a6133b1d353a01a86c1da92a9e38df06c6d3e08e2ae360ea051c1b60` |
| binutils | 2.10; arquivo SHA-256 `fd7d227c0dd15cf5448385e56b8ad8313cd491839834b57c0c086ac7b7819a15` |
| gbagfx | pret/pokeemerald commit `731ad5bfd6e6f265508d0efcca0ba42f9dcf5881`; 22 fontes com Git blob SHA-1 e SHA-256 verificados |

Fontes primárias: [khcom](https://github.com/Pheenoh/khcom/tree/5dc49b75068bfe24e07bdaf365570d64682680c3),
[Arm](https://developer.arm.com/Tools%20and%20Software/GNU%20Toolchain),
[binutils](https://ftp.gnu.org/gnu/binutils/),
[gbagfx](https://github.com/pret/pokeemerald/tree/731ad5bfd6e6f265508d0efcca0ba42f9dcf5881/tools/gbagfx).
Os manifestos de aquisição, checksum oficial Arm e logs ficam no diretório
privado. O snapshot público selecionado de parsers não foi expandido para
incluir indiscriminadamente toda a árvore de decompilação.

O `agbcc` foi compilado sequencialmente (`old_agbcc` e `agbcc`); seu build
paralelo inicial apresentou corrida em header gerado. O setup legado revisado
foi executado com `--jobs 4` em diretório temporário próprio **sem espaços**, pois
configure 2.10 falha em caminhos com espaços. O arquivo
`private/matching-v1/legacy-workdir.json` preserva a propriedade desse diretório.
`gbagfx` foi ligado à libpng já fornecida pelo runtime local. Com os binários
em PATH local e a ROM própria em `roms/B8CE.gba`, a sequência upstream foi
`tools/extract_assets.py us`, `configure.py --version us`,
`ninja -j4 build/us/ok`. A extração relatou 11.199 fontes verificadas e 6.274
decodificadas; dados raw continuam explicitamente opacos onde aplicável.

## Custo observado

Antes da adição de `direct_calls`, duas auditorias frescas em processos Python distintos, com cache de arquivos
já aquecido, demoraram 2,175 e 2,200 segundos; CPU total 2,188 e 2,211 segundos;
pico RSS 353.468.416 bytes no macOS. Incluem imports e auditoria, excluem
serialização do relatório. Não houve processos filhos. A comparação fria,
tokens do agente e pico do build matching não foram medidos; não há auditoria
anterior equivalente para declarar ganho. Números e método estão em
`private/matching-v1/performance.json`.
