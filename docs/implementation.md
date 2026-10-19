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
| Validação | Diagnóstico por ID para bytes, comandos, codecs e origem; candidato real exercitado | Layout/referências desconhecidos impedem aprovação geral |
| Fontes | Cinco fontes, 1.379 glifos; PNG↔bytes idênticos | Sem inventário completo de gráficos/vídeos |
| Extração gráfica | 4.900 recursos declarados reconstruídos byte a byte | Não comprova composição de telas, texto em imagens ou edição com crescimento |
| Piloto | Uma fala PT-BR com ã/á/é, observada na cena equivalente | Não fecha a prova vertical M2 |
| Baralhos | 24 acentos em três nomes de oito caracteres, digitados e retomados com ROM original | Teclado piloto com rótulos ASCII; duas oclusões parciais pela mão de seleção |
| Piloto gráfico | APERTE INICIAR nos cinco quadros do aviso; 57 capturas com letras exatas e restante da tela igual | Um recurso; título Riku, crescimento e recompressão pendentes |
| Créditos | 632 ponteiros conferidos; 631 linhas e 255 itens analisados; 388 desenhos rastreados em cada variante | Entrada diagnóstica; 627 linhas visitadas por término original do relógio; perfil acentuado pendente |
| Consumidores dos créditos | 750 fontes verificadas; produtor, tabelas e blitters indiretos examinados | Sustenta piloto US delimitado; não prova ausência global de endereços calculados |
| Recursos | 64 manifestos; 11.347 layouts e registros inventariados | 16.846 referências não resolvidas; não é round-trip gráfico completo |
| BPS | Vetores independentes, Floating IPS e reaplicação da candidata real | Auditoria de literais/distribuição pendente |
| Runtime | Build nativo macOS arm64; boot, abertura, diálogo e gameplay inicial Sora | Harness de diagnóstico; frontend final ausente |
| Save | SRAM 32 KiB; FILE 1 Sora e Quick Save gravados pelo jogo e retomados em processos novos, sem checkpoint | Outros slots, Riku, nomes acentuados em slot normal e migração ainda não verificados |
| Empacotamento | Fontes selecionadas por allowlist; dry-run npm do REA sem o subprojeto | Não é pacote executável de release |
| Portabilidade | Diagnóstico macOS arm64/x86_64 compilado e combinado; testes x86_64 via Rosetta | Sem QA Intel físico, Windows ou bundle final |
| CI | Dois workflows sem ROM, com actions/dependências fixadas; actionlint passou | Sem execução GitHub, upload ou release |

## Evidência retida localmente

Os caminhos abaixo são relativos ao subprojeto. Dados do jogo permanecem em
`private/` e não entram no staging de fontes.

- `private/reports/identity.json`: identidade da entrada fornecida.
- `private/reports/text-roundtrip.json`: prova por intervalo e SHA-256 integral.
- `private/localization/catalog-us.json` e `.csv`: inventário/edição dos textos.
- `private/fonts/us-v4/report.json`: fonte, métricas, ponteiros e glifos,
  incluindo à/À e distinção entre recurso e payload de tiles.
- `private/graphics/known-v3/report.json`: 4.900 reconstruções gráficas exatas.
- `private/reports/initial-map.json`: partição inicial de regiões e incertezas.
- `private/reports/asset-map-v3.json`: ampliação do mapa com layouts/registro
  de assets; 3.148.046 bytes ainda desconhecidos, sem espaço livre aprovado.
- `private/reports/dialogue-probe.json`: transformação experimental delimitada.
- `private/reports/static-validation-probe-v2.json`: candidata que cabe em bytes,
  conservando bloqueios de layout/referências no contrato geral.
- `private/reports/dialogue-visual-evidence.json`: inspeção visual do piloto,
  digests da candidata, imagem, trace e framebuffer; não é revisão humana.
- `private/reports/dialogue-probe-bps.json` e `dialogue-flips-reapply.json`:
  reaplicação BPS própria e independente, com o mesmo destino.
- `private/reports/credits-audit-v2.json`: ordem, comandos, glifos e larguras
  dos créditos, com evidência fonte/ROM separada de runtime.
- `private/reports/credits-entry-v1/evidence.json`: entrada diagnóstica e
  rastreamento dos créditos Sora/Riku; comparação sem perdas com o ledger.
- `private/reports/credits-consumers-v1/report.json`: corpus completo de fontes,
  referências e limites da conclusão sobre reuso de glifos.
- `private/runtime/dialogue-ptbr-main/`: execução de 12.000 frames da candidata.
- `private/runtime/tutorial-main/` e `your-*`: percurso original de diagnóstico.
- `private/reports/runtime-save-verification.json`: digests e capturas de save/reload real.
- `private/menu-probe/verification.json`: 24 acentos, limite da interface,
  Quick Save desde reset e retomada com ROM original; inclui as divergências de pixels.
- `private/reports/title-graphic-verification-v3.json`: comparação do aviso
  gráfico, preservação da animação e BPS reaplicado com Floating IPS.
- `private/reports/universal-diagnostic-v4.json`: binário com ambas as slices e checks via Rosetta; identidade do core corrigida.
- `private/reports/python-tests-v7.log`: suite Python pública sem ROM comercial.
- `private/reports/rea-pack-dry-run.json`: staging npm do REA, scripts desativados.

O mapa textual inicial classifica 7.358 regiões, com 33.122.404 bytes desconhecidos;
o mapa ampliado de assets tem 19.878 regiões e 3.148.046 bytes desconhecidos.
Detectou 8.666 palavras alinhadas iguais a endereços de textos; são **candidatas**,
não referências confirmadas. A partição não identifica espaço livre. O branch
ARM no cabeçalho deriva entrada em `0x080000C0`; não é um mapa de funções.
A rota ARM genérica do REA não foi apresentada como loader GBA validado.

## Validação e custos

A suite integrada Python passou **89 testes**, incluindo a interoperabilidade
com Floating IPS e o piloto gráfico, em Python 3.12.14. O build C++ passou **2/2 testes CTest**,
incluindo fixture ARM própria, framebuffer, entrada e SRAM/reabertura.
As execuções do jogo são evidência separada dos testes sintéticos.

O dry-run do pacote REA usou Node 24.18.0 e npm 11.16.0, com `--ignore-scripts`;
listou 67 arquivos e nenhum caminho do subprojeto/ROM/save/BPS. Isso não equivale
a executar os testes ou produzir o release do REA, que não foi modificado.

Medições do pipeline e do harness estão em `localization.md` e `runtime.md`.
Não há comparação cold/warm controlada, estimativa confiável de custo total da
tradução ou medição total de tokens do trabalho. Tempo de emulação acelerada
não comprova frame pacing, áudio em dispositivo nem desempenho de release.

## Marco M1 encerrado

As dez tarefas M1 estão verificadas. O baseline da ROM, o round-trip integral,
as dependências e a execução real têm evidências independentes. O percurso de
78.700 frames desde reset gravou Sora em Traverse Town; processos novos
carregaram apenas o save do cartucho e retomaram gameplay controlável.
A contagem OpenSpec é **15/73 tarefas concluídas**, incluindo a extração gráfica
M2.4; isso não representa uma
porcentagem de tradução, nem conclusão dos marcos seguintes.

## Trabalho ainda aberto

Rotas compactas exigem classificação por consumidor; a fonte `small` encontrada
em overlays/debug não mapeia acentos. O menu de baralhos Sora tem uma prova
delimitada de fonte, caixa e persistência em `menu-probe.md`; nomes arbitrários,
outros menus e Riku permanecem abertos. Créditos têm
codec/páginas próprios. Faltam caixas e referências por consumidor, mapa de ocupação e realocação,
gráficos/vídeos, prova vertical completa e tradução/revisão dos lotes. O piloto
nunca libera todos os textos por uma flag global.

As próximas verificações de fontes e créditos estão detalhadas em
`next-localization-step.md`; `asset-map.md` registra a ocupação conhecida.
O trabalho continua dentro do plano aprovado.

M4–M7 permanecem abertos: frontend completo, configurações de vídeo/áudio/entrada,
transações de cache/saves, QA integral de Sora/Riku, builds Windows/macOS universal,
instaladores, CI de distribuição, assinatura/notarização e preparação Android.
O repositório remoto e credenciais Apple ainda não foram fornecidos; sua ausência
não foi usada para omitir trabalho local nem para declarar esses marcos completos.

Nomes, marcas e Kingdom Hearts seguem a decisão explícita do proprietário em
`style-ptbr.md`. Nenhuma release, tradução 100% ou revisão humana foi declarada.
