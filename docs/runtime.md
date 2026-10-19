# Harness de diagnóstico M1

Este alvo é uma ferramenta de investigação local. Executa o core GBA, aceita um roteiro de botões e preserva evidências em um diretório escolhido. Não contém tradução, ROM, BIOS comercial, assets, instalador nem frontend final. O aplicativo e os requisitos de vídeo/áudio/configuração permanecem no marco M4.

## Dependências e build

`manifests/runtime-deps.json` é a fonte das versões, URLs e SHA-256. O CMake verifica os arquivos de libmgba 0.10.5 e SDL 3.4.18 antes de extrair. Um arquivo correspondente em `.deps/` evita outro download, sem dispensar o hash. `FETCHCONTENT_SOURCE_DIR_*` é uma opção de desenvolvimento do CMake que contorna o download: builds de release não poderão usá-la sem registrar/verificar os fontes substitutos.

O build mínimo precisa de compiladores C/C++20, SDK da plataforma, CMake 3.31.10 e Ninja 1.13.0. Na máquina de desenvolvimento, só CMake/Ninja foram instalados localmente, com Python 3.12.14 já fornecido pelo ambiente:

```sh
KHCOM_PYTHON='/Users/erikaraujo/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'
"$KHCOM_PYTHON" -m pip install --target .build-tools/python --no-deps cmake==3.31.10 ninja==1.13.0
./.build-tools/python/cmake/data/bin/cmake -S . -B build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_MAKE_PROGRAM="$PWD/.build-tools/python/bin/ninja"
./.build-tools/python/cmake/data/bin/cmake --build build --parallel 4
./.build-tools/python/cmake/data/bin/ctest --test-dir build --output-on-failure
```

Execute na raiz de `projects/khcom-ptbr`. Em outra máquina, selecione um Python existente compatível ou utilize CMake/Ninja já provisionados nas versões fixadas. Os hashes dos wheels macOS constam no manifesto. O procedimento não instala Homebrew, Node, Java ou outro produto.

O alvo `khcom-diagnostic` e o teste `khcom-core-tests` são produzidos sem qualquer ROM. Não há regra de instalação/distribuição neste marco. O build nativo executado usou AppleClang 21.0.0, SDK macOS 26.5 e arquitetura arm64. Também foi compilado x86_64 e seus dois testes passaram via Rosetta no mesmo Mac Apple Silicon. `lipo` produziu um executável com ambas as arquiteturas e `--help` foi executado por slice. Isso não testa hardware Intel nativo. A baseline de implantação foi definida em macOS 13.0; ainda não foi testada em macOS 13 ou Windows. O binário universal de diagnóstico não é um `.app` universal assinado; a validação deve ser repetida após alterações do runtime. Consulte `docs/ci.md` para os workflows e a distinção entre definição e execução de CI.

O core é estático, somente GBA, com renderer software. Frontends Qt/SDL2 upstream, debugger remoto, scripting, gravação, ZIP, PNG, FFmpeg e outras bibliotecas opcionais do mGBA estão desabilitados. SDL3 faz apenas a apresentação opcional neste harness. Mudar essas opções requer novo inventário.

## Contrato de execução

```sh
mkdir -p private/runtime
./build/khcom-diagnostic \
  --rom private/rom/B8CE.gba \
  --output-dir private/runtime/baseline-nova \
  --frames 1800 --capture-every 300
```

O diretório de saída deve ser **novo**, com pai existente. Destinos existentes são rejeitados. Mantenha ROMs, saves, capturas e traces do jogo em `private/`. O harness não envia dados à rede, não busca BIOS/configuração global e não grava ao lado da ROM. A identidade padrão é SHA-256 da revisão USA B8CE validada no manifesto de ROM do projeto. `--expect-sha256` exige uma seleção explícita quando se usa fixture própria ou uma imagem localizada validada; não detecta nem aprova automaticamente revisões alternativas.

Entrada opcional `--input-trace private/roteiro.csv`, UTF-8/ASCII:

```csv
frame,keys
1800,8
1801,0
1900,1
1901,0
```

O frame é zero-based, aplicado **antes** da execução desse frame. Cada linha substitui a máscara inteira, mantida até a próxima transição. Máscaras decimais: A=1, B=2, Select=4, Start=8, direita=16, esquerda=32, cima=64, baixo=128, R=256, L=512. Aceita comentários com `#`; rejeita linhas inválidas, frames duplicados, frames fora da execução e bits extras. Linhas podem vir fora de ordem: o parser canônico as ordena por frame.

`--save-in` carrega um save de cartucho em memória antes do reset. `cartridge.sav` só é escrito ao terminar uma execução bem-sucedida e quando o core possui um backend com bytes. A existência desses bytes **não prova** que o jogo gravou progresso válido: a inicialização pode criar um save sem slot. A retomada precisa ser confirmada por um novo processo e pelo menu do jogo, sem checkpoint.

`--checkpoint-out` grava separadamente `checkpoint.bin`, um estado de CPU/RAM para investigação. `--checkpoint-in FILE` permite continuar testes de botões sem repetir toda a abertura, exigindo `--save-in` pareado. O cabeçalho valida SHA-256 da ROM, versão exata do core, integridade do estado e digest do save de cartucho fornecido. A restauração só ocorre em um core novo. Checkpoints são privados, não são portáveis entre versões e **não demonstram save/reload do jogo**. O relatório identifica seu uso e o frame inicial do core; frames do trace/captura são relativos à execução atual. Para uma reprodução desde reset, concatene traces somando o frame inicial de cada segmento e execute sem `--checkpoint-in`.

`--preview --scale 1..6` cria uma janela SDL3, filtro nearest, 240×160 multiplicado pela escala. Só o fechamento da janela é uma entrada SDL aqui; botões do jogo vêm do trace. `--realtime` agenda frames segundo 280896 ciclos / 16777216 Hz (~59,7275 Hz). Não há stream de áudio para o dispositivo, menu, fullscreen, shader, opção de vsync, ajuste de aspecto, controle de DPI ou configuração persistente implementados neste diagnóstico. Esses requisitos continuam integrais em M4.

A ROM é limitada a 32 MiB, save a 128 KiB, trace a 1 MiB e arquivo de checkpoint a 2 MiB (o tamanho exato é validado pelo core). A execução aceita até 10 milhões de frames; capturas PPM (115215 bytes cada) têm orçamento de 1 GiB por execução. Esses limites de investigação impedem alocações/saídas ilimitadas e não são limites editoriais dos textos do jogo.

## Evidências e interpretação

- `report.json`: identidade selecionada, versão do core/harness, plataforma, contagem de frames, caminhos fornecidos, hash RGB canônico, backend/tamanho/hash do save, estatísticas de áudio e contagens de logs. `ok` significa conclusão do diagnóstico, não jogo homologado.
- `samples.csv`: framebuffer, entrada e contagens a cada 60 frames e no último frame solicitado.
- `input.csv`: trace normalizado efetivamente selecionado. As máscaras dos intervalos são mantidas até a próxima transição.
- `frame-N.ppm`: RGB 240×160 capturado no frame concluído N quando solicitado. Imagens são evidência privada e não entram no pacote público.
- `cartridge.sav`: snapshot do backend do cartucho, se detectado; não é uma declaração de progresso válido.
- `checkpoint.bin`: estado privado opcional para diagnóstico; não substitui nem certifica o save de cartucho.

O core usa o substituto de BIOS implementado pelo mGBA e pula a animação inicial da BIOS. Isso não pula a abertura do jogo. O relatório nunca marca boot visual, gameplay, tradução ou save/reload do jogo automaticamente. Um humano/agente deve revisar as imagens e registrar o percurso com os digests. O áudio é drenado e contado a 48 kHz, canais L/R; contagens são amostras de canais somadas, não frames estéreo. Amostras não nulas comprovam geração de sinal, sem atestar fidelidade/percepção nem saída sonora.

Logs DEBUG/INFO/STUB/GAME_ERROR não são impressos. WARN/ERROR/FATAL saem em stderr, no máximo 200 mensagens por execução; o relatório registra total, severidades emitíveis, emitidos e suprimidos. GAME_ERROR tem contagem própria e até oito exemplos truncados em 511 bytes de mensagem; eventos como escritas em IO somente leitura não são automaticamente tratados como crash. O JSON final fica em stdout. Falhas deixam evidências parciais no diretório novo e retornam erro com código; uma pasta parcial sem `report.json` de sucesso não comprova conclusão.

`wall_seconds` mede só o loop de emulação, incluindo captura e pacing. Para custo do processo completo, use o medidor do sistema separado. Ele não inclui build nem instalação. Não há comparação de desempenho de plataformas ou garantia de frame pacing neste marco.

## Verificação executada

Em 2026-10-18, `ctest` passou 2/2 testes no macOS arm64. O teste principal verifica SHA-256 com três vetores independentes conhecidos; executa instruções ARM escritas para este projeto, observa pixel vermelho e entrada A/R via KEYINPUT; escreve SRAM, clona os 32768 bytes e reabre em outro core. Também verifica preservação do buffer ROM, rejeição de bits de entrada inválidos, retomada por checkpoint e rejeição de checkpoint corrompido/truncado, ROM diferente e save de cartucho não pareado. A fixture não contém logo Nintendo nem código/assets do jogo. Esse teste não substitui save/reload do KHCoM.

Uma execução privada da ROM original por 1800 frames (`private/runtime/log-filtered`) mostrou a tela de título/PRESS START em captura revisada, identificou SRAM de 32768 bytes, gerou 2891764 amostras de canais (1359332 não nulas, pico 11268), preservou o hash em memória e não sinalizou crash. O teste SDL com driver dummy apresentou três frames; não certifica janela/DPI/monitor real. Gameplay e save real têm relatórios próprios a serem anexados pelo percurso de QA, não são inferidos deste baseline.

O percurso privado de inputs avançou pelo tutorial com salto/esquiva, recarga de cartas, L/R e Select, chegou a Traverse Town e acionou síntese de sala por golpe na porta. As capturas em `private/runtime/your-hold`, `your-select-hold`, `your-room` e `your-door-low-hit` registram essas transições. Isso comprova gameplay inicial controlável, sem homologar campanhas completas, multiplayer, visual de todas as telas ou persistência de progresso. A validação de save de cartucho depende do resultado separado de QA.

Save normal e retomada foram depois comprovados para **um slot Sora no início de Traverse Town**. O roteiro completo de 78700 frames em `private/runtime/your-save-from-reset` iniciou do reset, sem save de entrada e sem checkpoint, e mostrou “Save complete”, FILE 1, nível 01, andar 1, tempo 00:19:05. Os 32768 bytes de SRAM mudaram de SHA-256 `2d864c0b789a43214eee8524d3182075125e5ca2cd527f3582ec87ffd94076bc` para `343914b33160032a7e05175d103348f15854c83f1154b3dbfcd7ecf513639c4a`. O replay integral reproduziu os hashes de framebuffer e save obtidos na exploração com checkpoints.

Novos processos carregaram somente esse `cartridge.sav`, passaram por LOAD → FILE 1 e retomaram o campo; outra execução moveu Sora depois da carga. As capturas estão em `private/runtime/your-save-reload-slot`, `your-save-reload-field` e `your-save-reload-move`. Nenhuma dessas execuções finais carregou checkpoint. `private/reports/runtime-save-verification.json` registra digests, caminho dos traces, observações visuais e limites. Não foram verificados Riku, slots 2/3, Quick Save ou migração entre versões de ROM/core/aplicativo.

A execução medida com `/usr/bin/time -l` levou 1,02 s de parede, 0,64 s de CPU usuário e 0,01 s de CPU sistema, com RSS máximo de 44613632 bytes. O loop levou 0,318 s. Essa foi uma amostra com caches existentes, sem protocolo cold/warm; não há comparativo confiável. Filtrar logs suprimiu 11464 eventos de baixa severidade, sem warnings, nessa execução. Não foram medidos tokens do fluxo completo, memória de compilação ou áudio em dispositivo.

## Licenças e empacotamento futuro

O manifesto e `build/third-party-notices.txt` registram os avisos selecionados dos fontes fixados:

| Componente | Licença/origem observada |
| --- | --- |
| mGBA | MPL-2.0, `LICENSE` |
| blip_buf 1.1.0, incorporado ao core | LGPL-2.1-or-later, cabeçalho do `.c` e `license.txt` |
| inih | BSD-3-Clause |
| MurmurHash3 do mGBA | domínio público, declaração em `src/util/hash.c` |
| SDL3 | zlib |
| HIDAPI incorporado ao SDL | alternativa BSD-3-Clause selecionada |
| yuv2rgb incorporado ao SDL | BSD-3-Clause |

Essa lista e os avisos não são um pacote de conformidade de release. O link estático de blip_buf exige preparar os materiais e condições de relink/fontes correspondentes antes de distribuir; não se deve tratar toda a composição como apenas MPL. Fontes, notices, cabeçalhos auxiliares incorporados, backend final e licenças do próprio aplicativo precisam entrar na auditoria final M6. SDL inclui implementações auxiliares e headers de plataformas; a verificação final deve considerar os objetos efetivamente ligados em cada plataforma. Os binários diagnósticos permanecem privados/locais até isso ser resolvido.

As fontes oficiais usadas são [mGBA 0.10.5](https://github.com/mgba-emu/mgba/tree/0.10.5) e [SDL 3.4.18](https://github.com/libsdl-org/SDL/tree/release-3.4.18). Nenhuma licença dessas bibliotecas concede permissão sobre ROM, BIOS comercial, traduções preexistentes ou gráficos do jogo. O formato BPS não elimina a necessidade de auditar seus literais; esse gate pertence ao pipeline/empacotamento, não ao core.
