# Auditoria dos créditos

`tools/audit_credits.py` é uma inspeção somente leitura da revisão USA. Usa o
catálogo canônico de textos, o manifesto de assets e o comportamento dos
produtores/renderizadores do commit fixado em `manifests/upstream.json`.

```sh
.venv/bin/python tools/audit_credits.py --rom private/rom/B8CE.gba \
  --out private/reports/credits-novo.json
```

## Resultado executado

O array US `sStaffRollLines` tem 632 ponteiros e uma correspondência única de
2.528 bytes na ROM, em `0x09EF9F54`. Seus 631 registros antes do sentinel final
referenciam todos os 255 itens do pool textual de créditos. Os registros são
392 linhas de texto, 215 comandos de intervalo, 20 seções gráficas, três logos
e um encerramento de seção. Cobrir esse array não equivale a traduzir as imagens
das seções/logos nem os vídeos e quadros mostrados durante os créditos.

As tabelas de páginas, códigos, fontes, caracteres simples e larguras foram
conferidas contra os bytes da ROM. O modelo distingue bytes ASCII remapeados de
códigos de dois bytes em big-endian, preserva o estado de fonte entre linhas e
reinicia a cor por linha, conforme o produtor. Códigos sem mapeamento produzem
erro explícito; não são silenciosamente aceitos pelo fallback de glifo zero.

As fontes 0/1 usam respectivamente **63/58 índices** nos trechos efetivamente
desenhados por esse roteiro. Os outros 461/466 índices são **não observados**,
não livres. A auditoria não comprova ausência de outros consumidores ou
referências calculadas e não autoriza reaproveitá-los.

Há três avisos de avanço além da janela horizontal de x=16 até x=224 **na ROM
original**: linhas 169, 267 e 540, com extensões 6–234, 13–227 e 6–233 pixels.
São previsões estáticas, ainda sem captura dos créditos. Não foram classificadas
como falhas introduzidas por tradução nem como clipping observado em runtime.
O relatório privado preserva IDs, fonte, largura e referências por linha.

## Limites modelados

- `#0/#1`, `@`, `=/-/+`, `~`, `!`, `*D/*S/*J`, `<` e `[` têm semânticas
  separadas de texto. Prefixos e comandos não entram na contagem de glifos.
- O comando de duas colunas usa um buffer de 80 bytes: até 76 bytes no primeiro
  trecho, acrescido de três espaços e NUL; até 79 no segundo, acrescido de NUL.
- Cada desenho drena a fila antes e depois de enfileirar. São 255 posições úteis
  no anel de 256 entradas; igualdade dos índices indica fila vazia.
- Avanço visível e avanço dentro do tilemap de 240 pixels são resultados
  separados. Nenhum deles substitui a inspeção de pixels/acentos nas capturas.

Oito testes sintéticos exercitam remapeamento/ordem de bytes, fonte/cor,
colunas, limites exatos, códigos ausentes, truncamento, comandos e overflow
horizontal. Esses testes não contêm assets originais. O round-trip textual
integral continua pertencendo ao pipeline canônico de `text.py`; o auditor
não declara um segundo round-trip a partir de simples cópia dos bytes.

## Próximo gate

Faltam o perfil PT-BR com os 24 caracteres acentuados, glifos nos dois estilos,
prova de ocupação/referências e capturas dos créditos. Os símbolos presentes
em uma tabela CP932 não garantem suporte do renderer. A auditoria não altera a
ROM e não aprova uma tradução para distribuição.
