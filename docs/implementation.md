# Registro de implementação

Mudança: `khcom-ptbr-desktop`, schema `spec-driven`. Este registro descreve
somente verificações realizadas. O checklist oficial permanece em
`openspec/changes/khcom-ptbr-desktop/tasks.md`, na raiz RE ENGINE.

## Resultados locais

| Área | Resultado observado | Limite |
|---|---|---|
| Identidade | ZIP e ROM fornecidos correspondem aos digests registrados; origem preservada | Uma revisão USA B8CE |
| Importação | ROM renomeada e ZIP aceitos; seleção e limites testados | ZIP64/multivolume/criptografado não suportados |
| Texto | 12 manifests examinados, 10 com US, 6.736 itens | Inventário parcial do jogo |
| Round-trip | Todos os itens recodificados; ROM integralmente idêntica | 33.122.803 bytes preservados sem interpretação |
| Edição | CSV/JSON UTF-8, NFC editorial, IDs/controles/origem preservados | Reinserção geral de traduções ainda bloqueada |
| Fontes | Cinco fontes, 1.379 glifos; PNG↔bytes idênticos | Sem inventário completo de gráficos/vídeos |
| Piloto | Uma fala PT-BR com ã/á/é, observada na cena equivalente | Não fecha a prova vertical M2 |
| BPS | Vetores independentes, Floating IPS e reaplicação da candidata real | Auditoria de literais/distribuição pendente |
| Runtime | Build nativo macOS arm64; boot, abertura, diálogo e tutorial ativo | Harness de diagnóstico; frontend final ausente |
| Save | SRAM 32 KiB observada; clone/reload sintético testado | Save e retomada de progresso do jogo exigem evidência própria |
| Empacotamento | Fontes selecionadas por allowlist; dry-run npm do REA sem o subprojeto | Não é pacote executável de release |

## Evidência retida localmente

Os caminhos abaixo são relativos ao subprojeto. Dados do jogo permanecem em
`private/` e não entram no staging de fontes.

- `private/reports/identity.json`: identidade da entrada fornecida.
- `private/reports/text-roundtrip.json`: prova por intervalo e SHA-256 integral.
- `private/localization/catalog-us.json` e `.csv`: inventário/edição dos textos.
- `private/fonts/us-v4/report.json`: fonte, métricas, ponteiros e glifos,
  incluindo à/À e distinção entre recurso e payload de tiles.
- `private/reports/initial-map.json`: partição inicial de regiões e incertezas.
- `private/reports/dialogue-probe.json`: transformação experimental delimitada.
- `private/reports/dialogue-visual-evidence.json`: inspeção visual do piloto,
  digests da candidata, imagem, trace e framebuffer; não é revisão humana.
- `private/reports/dialogue-probe-bps.json` e `dialogue-flips-reapply.json`:
  reaplicação BPS própria e independente, com o mesmo destino.
- `private/runtime/dialogue-ptbr-main/`: execução de 12.000 frames da candidata.
- `private/runtime/tutorial-main/` e `your-*`: percurso original de diagnóstico.
- `private/reports/python-tests.log`: suite Python pública sem ROM comercial.
- `private/reports/rea-pack-dry-run.json`: staging npm do REA, scripts desativados.

O mapa inicial classifica 7.358 regiões, com 33.122.404 bytes ainda desconhecidos.
Detectou 8.666 palavras alinhadas iguais a endereços de textos; são **candidatas**,
não referências confirmadas. A partição não identifica espaço livre. O branch
ARM no cabeçalho deriva entrada em `0x080000C0`; não é um mapa de funções.
A rota ARM genérica do REA não foi apresentada como loader GBA validado.

## Validação e custos

A suite integrada Python passou **57 testes**, incluindo a interoperabilidade
com Floating IPS, em Python 3.12.14. O build C++ passou **2/2 testes CTest**,
incluindo fixture ARM própria, framebuffer, entrada e SRAM/reabertura.
As execuções do jogo são evidência separada dos testes sintéticos.

O dry-run do pacote REA usou Node 24.18.0 e npm 11.16.0, com `--ignore-scripts`;
listou 67 arquivos e nenhum caminho do subprojeto/ROM/save/BPS. Isso não equivale
a executar os testes ou produzir o release do REA, que não foi modificado.

Medições do pipeline e do harness estão em `localization.md` e `runtime.md`.
Não há comparação cold/warm controlada, estimativa confiável de custo total da
tradução ou medição total de tokens do trabalho. Tempo de emulação acelerada
não comprova frame pacing, áudio em dispositivo nem desempenho de release.

## Trabalho ainda aberto

Rotas compactas exigem classificação por consumidor; a fonte `small` encontrada
em overlays/debug não mapeia acentos. Menus de baralho US usam a fonte latina
segundo o código, mas suas caixas ainda exigem prova em runtime. Créditos têm
codec/páginas próprios. Faltam caixas e referências por consumidor, mapa de ocupação e realocação,
gráficos/vídeos, prova vertical completa e tradução/revisão dos lotes. O piloto
nunca libera todos os textos por uma flag global.

As próximas verificações de fontes e créditos estão detalhadas em
`next-localization-step.md` e continuam dentro do plano aprovado.

M4–M7 permanecem abertos: frontend completo, configurações de vídeo/áudio/entrada,
transações de cache/saves, QA integral de Sora/Riku, builds Windows/macOS universal,
instaladores, CI de distribuição, assinatura/notarização e preparação Android.
O repositório remoto e credenciais Apple ainda não foram fornecidos; sua ausência
não foi usada para omitir trabalho local nem para declarar esses marcos completos.

Nomes, marcas e Kingdom Hearts seguem a decisão explícita do proprietário em
`style-ptbr.md`. Nenhuma release, tradução 100% ou revisão humana foi declarada.
