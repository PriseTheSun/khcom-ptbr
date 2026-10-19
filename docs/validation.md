# Validação de candidatos textuais

O [ledger de eventos](event-text.md) acrescenta ocorrências, referências e
paginação vinculadas ao build matching, mantendo consumidores desconhecidos.
O [crédito traduzido](vertical-credit.md) demonstra a reinserção pública de um
cabeçalho real nas duas variantes; não concede aprovação ao restante do corpus.

```sh
.venv/bin/python tools/validate_localization.py --rom private/rom/B8CE.gba \
  --catalog private/localization/catalog-editado.json \
  --out private/reports/validacao-nova.json
```

O comando lê novamente a ROM e vincula o catálogo à identidade e aos fatos
extraídos pelo parser fixado. IDs, spans, aliases, codecs, limites e referências
de origem não podem ser editados para contornar um erro. Reinserção
e validação compartilham esse vínculo no produtor `bind_catalog`.

Cada candidato recebe diagnóstico por ID para NFC, codificação, comandos,
terminador final, alinhamento de code units e limite da reserva original.
Alterar quebras/comandos exige primeiro o contrato de seu consumidor; o
validador atual exige a mesma sequência. Metadados como `status=approved`
ou um nome em `reviewer` não substituem prova de fonte, caixa ou referências.

Resultado 0 significa que o relatório foi produzido sem candidatos bloqueados;
isso pode incluir um catálogo sem nenhuma edição. Código 2 significa candidatos
bloqueados com diagnóstico retido. Código 1 indica falha de entrada/proveniência
ou publicação da saída. Nenhum resultado aprova automaticamente a tradução ou
modifica a ROM.

## Créditos com contrato por ocorrência

O perfil explícito `staff-roll-ptbr-v1` permite gerar candidatas privadas de
créditos em posição fixa. A mesma função produz os diagnósticos e o plano de
bytes consumido pela reinserção; não existe recodificação independente depois
da validação. Acrescente `--profile staff-roll-ptbr-v1` ao comando acima e use:

```sh
.venv/bin/python tools/reinsert.py --rom private/rom/B8CE.gba \
  --catalog private/localization/catalog-editado.json \
  --profile staff-roll-ptbr-v1 \
  --out private/rom/creditos-candidata.gba \
  --report private/reports/creditos-reinsercao.json
```

Cada ID é vinculado a **todas** as suas ocorrências no roteiro. O validador
reconstitui a fonte de entrada, mantém prefixos de fonte/cor/alinhamento e
verifica o orçamento de bytes, fila de glifos, avanços e pixels dos glifos.
Uma ocorrência que cabe na fonte 0 pode exceder a fonte 1; nesse caso o ID
inteiro fica bloqueado. O renderer literal não substitui variáveis nessa rota.
O intervalo conservador de avanço horizontal é `[16, 224)` e cada ocorrência
admite uma linha. Duas colunas, linhas estruturais/vazias, glifos sem contexto
observado e as ocorrências 627–630, posteriores ao fim observado da rolagem,
continuam bloqueados. Cor/alinhamento preservados não dispensam inspeção visual
da nova candidata.

O catálogo original conserva CP932. Somente esse perfil seleciona os 24 códigos
dos acentos e reconstrói as quatro regiões de fontes/larguras. Nenhuma fonte é
gravada quando não há edição. Uma tradução exige exatamente um `{END}` final;
Unicode decomposto, caracteres invisíveis e controles inesperados são erros.
Os glifos admitidos são os observados no roteiro US, os 24 acentos e os rótulos
autorais do piloto V2, por fonte; isso não libera automaticamente todo ASCII.

As 631 referências do roteiro são verificadas em bytes. A varredura adicional
de palavras alinhadas de 32 bits retém valores exteriores/interiores ao início
das entradas como **candidatos**, não como prova de ponteiro ou espaço livre.
IDs com tais candidatos não são editáveis até sua classificação por evidência.
O relatório preserva aliases e declara o limite desta investigação.

Com `--matching-tree /caminho/khcom`, o produtor `khcom.matching` verifica
novamente `build/us/com_us.gba`, ELF, mapa e os objetos do build. O caminho
consome os bytes já validados de GBA/ZIP; não aceita JSON de fatos editável
como autorização. O perfil consome a classificação do produtor, sem interpretar
ELF ou tiles novamente. Sete palavras foram comprovadas como dados codificados
em três sprites e um bloco de áudio. A referência adicional a `SpaceText` é
real e permanece bloqueada até o contrato do consumidor adicional. Ausência
de relocação, por si só, não é interpretada como ausência de referência.
Hashes, argumentos de origem, provas dos oito candidatos e limitações ficam
no relatório. Nenhum desses fatos anuncia espaço livre.

O plano valida identidade, hash de cada reserva, alinhamento das referências,
intervalos sem sobreposição e preservação dos bytes externos. Apenas o novo
payload é escrito; a cauda remanescente da reserva fica intacta. Não há expansão
nem realocação. Qualquer candidato bloqueado impede a ROM inteira; o relatório
de recusas permanece disponível. Status/revisor do catálogo não autorizam nada.
Uma candidata admitida mantém `candidate_runtime_verified=false` e
`release_approved=false`.

## Evidência local

A candidata privada da primeira fala, já observada separadamente em runtime,
foi submetida pelo mesmo catálogo geral em
`private/localization/catalog-static-probe.json`. O relatório
`private/reports/static-validation-probe-v2.json` confirma que seus 42 bytes
cabem na reserva de 52, mas mantém dois bloqueios no contrato geral:
`references_unknown` e `layout_unknown`. O piloto delimitado não foi convertido
em aprovação de todos os consumidores nem em um bypass para reinserção em massa.

A reinserção pública das quatro linhas autorais do piloto de créditos V2 foi
executada com o ZIP e membro explícito. A candidata reproduziu **byte a byte**
o piloto: SHA-256
`dfff8d06c64071155a7cfa278d6df8112dcd17e3db53902ed91a7d6b04922f52`,
1.169 bytes alterados em oito spans. Não houve nova execução do jogo nesta
comparação. A execução sem traduções e com perfil explícito preservou a ROM
inteira. Uma alteração de prefixo de fonte foi recusada com diagnóstico e sem
gravar ROM. A origem e os relatórios anteriores foram preservados; os hashes
estão em `private/localization/credits-reinsertion-v1/equivalence.json`.

Os dez testes adicionais de contratos de créditos usam dados autorais e
cobrem múltiplas ocorrências/fontes, estouro visual que cabe em bytes, glifo
desconhecido/cortado, prefixos, filas, referências adicionais/interiores,
terminadores, fontes não observadas, sobreposição e identidade do plano.
O conjunto focalizado de texto/catálogos/créditos executou 49 testes com sucesso.

O ensaio `catalog-matching-reference-probe.json` ficou bloqueado sem matching
por seis valores interiores. Repetido com a árvore matching validada, o mesmo
texto foi admitido como candidata estática, com os seis valores preservados no
relatório como coincidências de dados gráficos comprovadas. Não foi gerada ROM
nem houve execução desse texto; o ensaio verifica o contrato de referências.

Os testes com fontes/bytes próprios verificam estouro, código não mapeado,
terminador antecipado, NUL literal, comandos codificados alterados e adulteração de aliases/limites,
além de um candidato que cabe em bytes mas continua sem aprovação visual.

## Próximos contratos

A tarefa M2.7 permanece aberta até a integração das referências comprovadas
por consumidor. M2.8 exige métricas, caixas, linhas, variáveis e captura de cada
renderer. Não há limite global de pixels inventado a partir da largura do GBA;
textos de créditos, menus e diálogo precisam de perfis próprios. O campo de
ponteiros desconhecido permanece `null`, em vez de virar uma lista vazia.
