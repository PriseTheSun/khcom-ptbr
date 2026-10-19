# Mapa de ocupação inicial dos recursos

```sh
.venv/bin/python tools/map_rom.py --rom private/rom/B8CE.gba \
  --include-assets --out private/reports/asset-map-novo.json
```

Os 64 manifestos `config/assets/*.yaml` da revisão fixada foram adicionados ao
mesmo manifesto de proveniência usado pelos codecs. O download inicial foi
conferido pelo identificador do objeto Git e fixado por SHA-256; leituras
subsequentes usam esses hashes. Não foi executado o extrator/build upstream.

O parser proprietário do formato verifica os objetos, alinhamentos e limites
de cada layout. Os intervalos são confrontados com a ROM identificada e
combinados com os intervalos textuais existentes. Sobreposição ou identidade
divergente é erro, nunca uma preferência silenciosa por uma das fontes.

## Resultados locais

- 11.347 recursos, somando 29.974.358 bytes, sem sobreposição entre os layouts.
- 1.387 registros com correspondência integral de campos/padding conhecido;
  3.925 com correspondência parcial, mantendo os campos desconhecidos explícitos.
- 6.034 recursos com layout inventariado, sem recodificação do payload nesta
  etapa. Incluem gráficos, áudio, animações e outros formatos.
- Um preenchimento de 256 bytes coincide exatamente com o manifesto, mas
  ainda não foi demonstrado que possa ser reutilizado.
- 16.846 campos simbólicos de referência não resolvidos; seus valores
  observados foram preservados no relatório.
- A partição conjunta tem 19.878 regiões e 3.148.046 bytes ainda desconhecidos.

O relatório está em `private/reports/asset-map-v3.json`. O mapa anterior continua
preservado como evidência da etapa textual inicial. Os 8.666 valores alinhados
iguais a endereços de textos continuam classificados como candidatos; a inclusão
dos layouts não transforma essa busca em um call graph ou em xrefs confirmadas.

O inventário separa `entry_name` e referências `palette_entry`/`borrowed_tiles_entry`
dos `emitted_symbols` calculados pelo parser proprietário. O nome estável da entrada
é a chave das referências do manifesto; não é necessariamente o símbolo C/assembly.
Os relatórios anteriores a v3 usavam rótulos `symbol` ambíguos e são substituídos
por v3 para consumo. Os intervalos, contagens e checks de bytes não mudaram.

O dono da interpretação de um `sprite_sheet` distingue início do recurso,
frames/animações e payload de tiles. O inventário geral **não** resolve símbolos
de tiles para o início do recurso. Referências a esses símbolos permanecem
desconhecidas até uma interpretação específica, como a já feita para as fontes.

## Alcance

Este mapa não é inventário visual completo de texto em imagens. Tampouco é
round-trip dos 11.347 recursos. Os cinco atlas selecionados possuem provas
próprias de PNG↔bytes; os demais mantêm a classificação exata de verificação.
Registros parciais nunca são contados como ponteiros integralmente verificados.

O mapa prepara a tarefa de ocupação/realocação, que continua aberta: faltam
referências indiretas/calculadas, orçamento de RAM e uma realocação demonstrada.
Nenhuma região foi designada como livre e o tamanho do cartucho não foi ampliado.

## Custo observado

Uma execução com fontes já baixadas e caches existentes levou 3,79 s de parede,
3,71 s de CPU usuário e 0,06 s de CPU sistema, com RSS máximo de 247.463.936
bytes. O fluxo usa um único processo Python, sem subprocessos de extração.
Medição: `/usr/bin/time -l`, em `private/reports/asset-map-measured.time.txt`.
Não houve protocolo cold/warm controlado, comparação equivalente anterior ou
medição de tokens; ampliar a cobertura não é apresentado como ganho de desempenho.
