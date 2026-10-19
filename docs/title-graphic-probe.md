# Piloto gráfico da tela de título

`tools/probe_title.py` transforma o aviso gráfico `PRESS START` em
**APERTE INICIAR** nos cinco quadros de `gTitlePressStartTiles`, na revisão
USA fixada. A receita contém desenhos próprios de letras 5×7; lê o restante
dos pixels da ROM fornecida localmente. Nenhum bitmap original foi colocado
nas fontes públicas do projeto.

```sh
.venv/bin/python tools/probe_title.py \
  --rom private/rom/B8CE.gba \
  --out private/rom/B8CE-title-probe.gba \
  --report private/reports/title-graphic-probe.json
```

A saída exige caminhos novos dentro de `private/`. O exemplo usa os nomes
da execução já realizada; escolha outros nomes para repetir sem sobrescrever.
O comando não altera a origem e não aprova uma distribuição.

## Representação preservada

O recurso de 2.090 bytes começa em `0x0977153C`. A receita mudou **298 bytes**
nos tiles, conservando os registros OAM, animações, paletas, endereços, tamanho
do recurso e os demais bytes da ROM. Mantém o ícone animado do botão e a barra.
Os cinco quadros foram decodificados novamente, com igualdade de todos os
pixels solicitados.

O editor conserva a alocação original de tiles em vez de empacotar novamente.
Cada uso de um tile compartilhado precisa produzir os mesmos bytes; divergência
gera erro que exige resolver realocação. Também rejeita banco de paleta errado,
pixels fora das peças e dimensões incompatíveis. Quatro testes com sprites
próprios exercitam compartilhamento, flips, animação, composição e rejeições.
Não há consumidor por empréstimo declarado para esse recurso nos 64 manifestos;
isso não equivale a um grafo completo de consumidores no código.

## Verificação executada

A candidata tem SHA-256
`562c09cde6de9e098c0544ab9fcbc091a5abbfbfd08283f34e4e452ec6e6d113`.
O harness nativo macOS arm64 executou original e candidata desde reset,
sem save/checkpoint, durante 1.440 frames, capturando a cada sete frames.

- Foram comparadas 206 capturas equivalentes. As diferenças ficam no aviso
  em sua entrada na tela e posição final; os limites por frame foram retidos.
- Nas 57 capturas estáveis entre os frames 1.050 e 1.440, a composição das
  letras coincide pixel a pixel com a receita; todos os pixels fora da caixa
  do texto são idênticos à execução original.
- As capturas contêm cinco estados distintos do ícone, preservados entre
  original e candidata. A inspeção visual confirmou texto legível, sem corte.
- Outra execução acionou Start e chegou ao menu inicial. Os demais rótulos
  desse menu continuam originais; este piloto não declara a tela traduzida.
- O BPS de **442 bytes** foi reaplicado pelo gerador/aplicador do projeto e
  por Floating IPS. Ambos produziram exatamente o SHA-256 da candidata.

`private/reports/title-graphic-verification-v3.json` registra hashes de código,
binário, ROMs, patch, traces e capturas; `private/title-probe/verify.py` repete
a comparação. A imagem `private/runtime/title-graphic-probe-v1/frame-1200.png`
mostra o aviso, e `private/runtime/title-probe-start/frame-1900.png` mostra
o menu depois de Start. Essa inspeção pelo agente não é revisão humana.

O verificador exige as mesmas 206 capturas esperadas nas duas pastas, término
no frame 1.440, 57 comparações estáveis e cinco estados do ícone. Inventários
vazios ou com uma captura faltante foram rejeitados em verificações dirigidas.
O executável usado nestas capturas foi retido em
`private/toolchain/before-core-version-fix/`; uma correção posterior do gerador
de versão não substitui a identidade do binário que produziu esta evidência.

Permanecem abertos a variante de título Riku, a tradução das demais imagens,
recompressão, crescimento/realocação, consumidores externos e auditoria dos
literais do BPS. O piloto avança a prova gráfica M2.14, sem concluir M2.10
ou o marco vertical completo.
