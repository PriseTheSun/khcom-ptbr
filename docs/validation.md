# Validação de candidatos textuais

```sh
.venv/bin/python tools/validate_localization.py --rom private/rom/B8CE.gba \
  --catalog private/localization/catalog-editado.json \
  --out private/reports/validacao-nova.json
```

O comando lê novamente a ROM e vincula o catálogo à identidade e aos fatos
extraídos pelo parser fixado. IDs, spans, aliases, codecs, limites e referências
de origem não podem ser editados para contornar um erro. Reinserção sem edição
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

## Evidência local

A candidata privada da primeira fala, já observada separadamente em runtime,
foi submetida pelo mesmo catálogo geral em
`private/localization/catalog-static-probe.json`. O relatório
`private/reports/static-validation-probe-v2.json` confirma que seus 42 bytes
cabem na reserva de 52, mas mantém dois bloqueios no contrato geral:
`references_unknown` e `layout_unknown`. O piloto delimitado não foi convertido
em aprovação de todos os consumidores nem em um bypass para reinserção em massa.

Os testes com fontes/bytes próprios verificam estouro, código não mapeado,
terminador antecipado, NUL literal, comandos codificados alterados e adulteração de aliases/limites,
além de um candidato que cabe em bytes mas continua sem aprovação visual.

## Próximos contratos

A tarefa M2.7 permanece aberta até a integração das referências comprovadas
por consumidor. M2.8 exige métricas, caixas, linhas, variáveis e captura de cada
renderer. Não há limite global de pixels inventado a partir da largura do GBA;
textos de créditos, menus e diálogo precisam de perfis próprios. O campo de
ponteiros desconhecido permanece `null`, em vez de virar uma lista vazia.
