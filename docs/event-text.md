# Ocorrências e paginação dos diálogos US

`audit_event_text.py` liga o catálogo aos scripts da ROM matching. A auditoria
local encontrou **197 eventos e 2.940 ocorrências**: **2.923** foram medidas pelo
modelo US; **17** conservam codec japonês e permanecem desconhecidas para esse
renderer. Isso mede o roteiro, não prova alcançabilidade na campanha.

```sh
.venv/bin/python tools/audit_event_text.py \
  --rom private/rom/B8CE.gba \
  --matching-tree private/matching-v1/khcom-5dc49b75068bfe24e07bdaf365570d64682680c3 \
  --out private/reports/eventos-nova-auditoria.json
```

A ferramenta também aceita ZIP com `--member`. Revalida ROM, reconstrução byte
a byte, ELF, mapa, objetos e fontes fixadas. Não recebe JSON de evidência como
autorização. A saída é exclusiva em `private/`; a origem permanece intacta.
A execução está em `private/reports/event-contract-v1/audit-v2.json`, com seu
ZIP/member de entrada.

## Representação e cobertura

`event_contract.py` interpreta `gEventSequenceDefs`, objetos `EventSequenceDef`
de 48 bytes e registros `MessageScriptEntry` de 24 bytes. Cada ligação índice →
definição → script → texto precisa da relocação ABS32 exata e dos bytes
matching. Símbolos ambíguos não são escolhidos pela ordem da tabela.

Cada ocorrência preserva evento, índice, endereço/hash, IDs, retrato, expressão,
flags, atraso, frame e referências. `KEEP` herda a posição anterior; uma primeira
posição desconhecida continua desconhecida. Retrato ausente usa X=46. Os demais
usam as tabelas X/Y da ROM, com ajuste vertical US de −2 pixels. Evento 11 usa
paleta alternativa 3; 3/134/156 usam 5; outros inicializam somente a normal.

As referências interiores e consumidores adicionais permanecem separados dos
ponteiros de scripts. Dois textos de `card_message_text` são ligados ao renderer
pelo ponteiro, independentemente do nome do pool. Seus outros destinos continuam
exigindo contratos próprios. Casos preservados na auditoria:

- As 17 ocorrências `jp` pertencem aos eventos 14, 20, 62, 69, 71, 127, 128 e
  196. A aparência legada/dummy não concede dispensa linguística.
- `gEventTextUs_08FEE02C` não tem ocorrência no índice examinado.
- `gEventTextUs_0900868C` tem referência adicional em `card_msgwin.o`.
- `gObtainedWorldCardsText` e `gOwlTalkText` são compartilhados com outro pool.

Ausência de relocação não prova ausência de endereço calculado. Campanha,
desbloqueio e progressão não são inferidos do índice: `runtime_observed=false`
e `edit_authorized=false` são deliberados no ledger estático.

## Medição e verificação

`event_layout.py` reproduz `LayoutMsgGlyphsPage` US: u16le, índices latinos,
ícones explícitos, terminador, quebras e controles de paleta. Usa as 256 métricas
verificadas, respeitando a conversão assinada feita pelo jogo. A quebra ocorre
**depois** do glifo que leva X além de 155 pixels. Linhas avançam 12 pixels;
Y maior que 24 gera continuação. Uma quebra imediatamente antes de END pode
gerar uma página vazia. A paleta reinicia por chamada/página.

O renderer escreve o slot atual antes de decidir se a unidade é NL: uma quebra
após 128 glifos também excede as 128 estruturas. O modelo rejeita isso, código
sem mapeamento, paleta sem inicializador, controles incompatíveis e controle
de paleta imediatamente antes de END. O último defeito foi observado no
[experimento de fontes](font-runtime-coverage.md).

Os resultados descrevem posições, avanços, bounds e páginas; não inventam uma
caixa universal de 155 pixels, aprovação de recorte ou variáveis formatadas por
outro consumidor. Doze testes autorais cobrem identidade, referências, aliases,
herança, registro incompleto, paleta, ícones, paginação, capacidade e erros.

`private/reports/event-contract-v1/runtime-model-comparison.json` compara quatro
execuções preservadas do evento 156: origem, retorno de 12 glifos e posições/
avanços das **48 ocorrências** coincidem com registradores e pixels nativos.
Não houve nova execução nessa comparação. Paginação múltipla continua com prova
de fonte/testes, separada de runtime.

Fontes fixadas em `5dc49b75068bfe24e07bdaf365570d64682680c3`:
[`event_message.c`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/src/evt/event_message.c),
[`event_index_data.c`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/src/evt/event_index_data.c),
[`msg_types.h`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/include/evt/msg_types.h) e
[`msg.c`](https://github.com/Pheenoh/khcom/blob/5dc49b75068bfe24e07bdaf365570d64682680c3/src/msg/msg.c).
