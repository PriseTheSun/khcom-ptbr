# Lotes editoriais sem lacunas de IDs

`plan_batches.py` extrai novamente o catálogo e os recursos da ROM original,
mantendo um responsável por ID. Agrupa textos por domínio/unidade da cena e
recursos pelo dono declarado no inventário. Uma cena longa recebe partes
contíguas; referências compartilhadas continuam associadas ao mesmo texto.
O limite padrão é 48 itens ou 12.000 caracteres por sessão. É um orçamento
editorial ajustável, não limite de bytes do jogo nem estimativa de tokens.

```sh
.venv/bin/python tools/plan_batches.py --rom private/rom/B8CE.gba \
  --events private/reports/event-contract-v1/audit-v2.json \
  --out private/lotes-novos
.venv/bin/python tools/assemble_batches.py --rom private/rom/B8CE.gba \
  --plan private/lotes-novos/plan.json --sessions private/lotes-novos/text \
  --out private/catalogo-reunido.json
```

O primeiro inventário gerou **668 lotes**: 284 sessões textuais para os 6.736
IDs e 384 grupos de recursos para 11.347 IDs. A união contém exatamente 18.083
IDs, sem lacuna ou dupla contagem. `sessions.md` materializa uma tarefa de
classificação, tradução aplicável, revisão e validação por lote. As sessões JSON
UTF-8 preservam os IDs e metadados de origem do catálogo; não copiam texto para
fontes públicas. Originais e dados de edição ficam em `private/`.

O ledger de EventMessage fornece retrato, posição, paleta e layout por
ocorrência, com hash da investigação. Campanha, desbloqueio e percurso de QA
continuam desconhecidos quando não demonstrados; um número de evento não é
inferido como prova de uma campanha. Nenhum grupo de recursos é classificado
automaticamente como “sem texto” pelo formato ou nome do arquivo.

A reunião rejeita sessão ausente/trocada/duplicada, ID extra, alteração de origem
e plano de outra revisão. Reutiliza `bind_catalog`, o mesmo dono da distinção
entre origem imutável e campos editáveis. Não aplica patch nem libera textos
que apenas cabem em bytes. O catálogo reunido ainda passa pelo validador por
consumidor, reinserção, BPS, execução e cobertura.

O plano é uma partição do inventário **conhecido**. Descobertas novas reabrem
o plano; caminhos/variantes ainda desconhecidos não somem da cobertura. A
materialização final dos lotes no OpenSpec e os percursos das duas campanhas
permanecem parte de M3/M5. Não foi marcada tradução ou revisão por gerar esses
arquivos. Evidência inicial: `private/batches-v1/`.
