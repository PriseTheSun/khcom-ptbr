# Aplicativo desktop experimental

`khcom-desktop` é um aplicativo SDL3 executável em C++, com mGBA 0.10.5 embarcado, menu em PT-BR, áudio estéreo, teclado/gamepad, armazenamento local e aplicação BPS. Não requer Python durante o uso. A interface declara **tradução experimental e parcial**: os pilotos disponíveis não equivalem à tradução integral das campanhas.

## Uso e controles

O usuário seleciona **Importar minha ROM…** e fornece sua edição USA B8CE revisão 0, em `.gba` ou `.zip`. Um ZIP com várias entradas `.gba` exige seleção explícita. A origem precisa ter 33.554.432 bytes e SHA-256 `6f6e7b61bb7b6ef7e2bea6e9dd01e70570a715835cc3713abe86186fd2c4e28d`; renomear outra revisão ou fornecer uma ROM modificada não satisfaz essa identidade.

O aplicativo procura `localization/manifest.json` na pasta base SDL. No `.app`, a base é `Contents/Resources/`; no Windows, é a pasta do executável. **Selecionar pacote PT-BR…** também permite escolher um manifesto local. Não há busca/download de ROM, BIOS ou assets. O core usa sua implementação de BIOS HLE. A fonte da interface é Droid Sans sob Apache-2.0; as fontes do jogo são distintas.

| Função GBA | Teclado padrão | Gamepad padrão |
|---|---|---|
| A | X | Sul (A/Cruz) |
| B | Z | Leste (B/Círculo) |
| Start | Enter | Iniciar |
| Select | Backspace | Voltar |
| Direções | Setas | Direcional ou analógico esquerdo |
| R | S | Ombro direito |
| L | A | Ombro esquerdo |
| Menu do aplicativo | Escape/F1 | Guia |

No menu, Tab/setas e Enter navegam e confirmam. A aba Controles remapeia as dez funções, troca vínculos em conflito e ajusta a zona morta analógica. Escape/F1 e Guia permanecem reservados ao menu. O backend SDL oferece navegação por gamepad e abertura/fechamento de dispositivos; a verificação com gamepad físico ainda deve constar do relatório de QA da plataforma.

A aba Vídeo oferece escala física inteira 1x–6x, ajuste inteiro à área disponível, preenchimento esticado explícito, tela cheia, vsync e filtros nítido, linear e CRT. Escala que não cabe apresenta aviso; não corta o framebuffer para caber. A origem continua 240×160 (3:2). O CRT usa `SDL_GPURenderState`, com variantes MSL/SPIR-V/DXIL provenientes do código SDL fixado; renderers sem suporte apresentam fallback explícito para pixels nítidos. Não há compilador de shader externo durante o uso.

O ritmo da emulação é `280896 / 16777216` segundos por quadro, aproximadamente 59,7275 Hz, acumulado pelo relógio monotônico. A cadência da apresentação não escolhe a velocidade do GBA. Pausa, perda de foco e intervalo de suspensão superior a 250 ms descartam o crédito de tempo; não aceleram o jogo para compensar uma suspensão. O áudio recebido do core em 48 kHz estéreo S16 é entregue a `SDL_AudioStream`, com volume/silêncio e limite de fila de 250 ms. A fila é limpa ao pausar/perder foco e a saída pode ser reconectada.

## Dados, atualização e recuperação

O diretório padrão vem de `SDL_GetPrefPath("KHCoM-PTBR", "desktop")`:

- macOS: `~/Library/Application Support/KHCoM-PTBR/desktop/`;
- Windows: `%APPDATA%/KHCoM-PTBR/desktop/`.

`--data-dir DIRETORIO` escolhe outro local. Um lock de arquivo do sistema impede dois escritores simultâneos no mesmo diretório. `config.json` guarda opções e mapeamentos; dados inválidos são preservados em `.invalid-*`, com aplicação dos padrões. Restaurar padrões não remove saves.

A identidade de cache inclui SHA-256 da origem, do patch e do destino, mais o contrato `khcom-bps-v1`. O patch tem limites de tamanho e comandos, verifica os três CRCs BPS e os hashes/tamanhos do manifesto. Toda abertura revalida o destino. Repetir a instalação usa cache válido sem regravá-lo; cache adulterado é recusado e pode ser reconstruído com a origem e o pacote válidos. Os bytes originais nunca são reescritos.

`active.json` contém a identidade atual e, quando existe, `previous_installation`. Atualização e rollback trocam ambas em **um único rename atômico**. Cancelamentos observados antes do commit preservam o ponteiro anterior; cancelamento depois do commit não transforma uma ativação concluída em falha. O manifesto ativo e os saves ficam fora do bundle assinado.

A aba Dados oferece três perfis, exportação/importação `.khcs`, restauração de backup e rollback de pacote. `.khcs` é um envelope CBOR único com SRAM de 32.768 bytes, identidade B8CE, versão de compatibilidade e SHA-256; não é um savestate. Saves são comparados e gravados a cada cinco segundos, ao pausar/perder foco e ao sair, com `.bak` da geração anterior. O save normal do próprio jogo continua necessário para selecionar progresso ao reiniciar. Importação não reutiliza a sessão anterior depois de substituir a geração persistida. Recuperação preserva o arquivo substituído em `.before-restore-*`. Um erro de gravação mantém a sessão em memória e impede a saída normal até retry.

Gravações usam arquivo exclusivo no mesmo diretório, `fsync`/`FlushFileBuffers`, âncora hard link e registro de ownership com identidade de arquivo. A âncora mantém o inode/file ID atribuído ao temporário; nome ou PID isolados não autorizam remoção. Na recuperação, identidade trocada e registros desconhecidos são preservados; limpeza incompleta conserva o registro para retry. Após commit, a limpeza remove apenas o temporário/âncora/registro, nunca o destino. A aba Dados permite **Tentar limpeza novamente**. O armazenamento precisa admitir hard links e rename atômico (APFS/NTFS são os alvos); uma falha desses recursos é reportada. Um processo morto antes de conseguir criar o registro pode deixar um arquivo sem ownership comprovado, que não é removido automaticamente. Não se alega tolerância a qualquer falha física de armazenamento.

## Build e núcleo portátil

```sh
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
ctest --test-dir build --output-on-failure
```

Os hashes/URLs/licenças estão em `manifests/runtime-deps.json`. As dependências gráficas são SDL3 e Dear ImGui; nlohmann/json e miniz pertencem ao modelo de patch/armazenamento. O CRT deriva do exemplo SDL fixado e do efeito CC0 de pxlforge, com atribuição nos avisos. O MSVC usa CRT estático `/MT` (`/MTd` em Debug). O empacotamento e os bundles de fontes correspondentes são descritos separadamente em `docs/distribution.md`/`docs/ci.md`, quando presentes.

```sh
cmake -S . -B build-portable -G Ninja \
  -DKHCOM_BUILD_DESKTOP=OFF -DKHCOM_BUILD_DIAGNOSTIC=OFF
cmake --build build-portable --parallel
ctest --test-dir build-portable --output-on-failure
```

Esse modo compila `khcom_core` e `khcom_desktop_model` sem SDL/ImGui/fonte gráfica; ambos os executáveis SDL são desabilitados automaticamente quando `ANDROID` está definido. A UI, áudio e entrada Android ainda precisam de adaptadores próprios. O build portátil no host não comprova build NDK, APK, ciclo de vida Android ou desempenho em dispositivo.

## Verificação registrada

`tests/cpp/desktop_tests.cpp` cobre comandos BPS independentes, CRC e offsets inválidos, ZIP ambíguo/traversal, configuração corrompida, envelope de save/backup/perfis, cache key, escalas e relógio em apresentações sintéticas de 60/120/144/500 Hz. A recuperação de temporários usa fixtures com IDs reais: payload parcial, nome reutilizado, commit já concluído e retry. Em POSIX, a suíte exercita permissão de limpeza e falha de escrita com `RLIMIT_FSIZE`; isso é um limite real do kernel, **não um ensaio ENOSPC em disco cheio**. A suíte padrão não contém ROM/BIOS/assets do jogo.

O executável opcional `khcom-storage-integration` recebe explicitamente a ROM/ZIP e dois pacotes privados:

```sh
build/khcom-storage-integration ORIGINAL.zip \
  PACOTE_V1/manifest.json PACOTE_V2/manifest.json DIRETORIO_NOVO
```

Ele verifica origem preservada, cache repetido, cancelamentos em validação/trabalho/ativação, resultado após cancelamento tardio, atualização, rollback nos dois sentidos e cache adulterado/reconstruído. O diretório deve ser novo para não sobrescrever evidência anterior. Não é instalado no pacote final e não afirma gameplay.

Para capturas/reprodução limitada do desktop:

```sh
build/khcom-desktop --hidden --mute --frames 1800 \
  --data-dir DADOS_PRIVADOS --rom ORIGINAL.zip --package PACOTE/manifest.json \
  --filter 2 --report RELATORIO.json --capture FRAME.ppm --screenshot JANELA.ppm
```

`--hidden` usa GPU/áudio reais com janela oculta; `--headless` usa dispositivos dummy e não prova hardware. `--ui-frames N` mantém o menu aberto para captura. `--capture` lê o framebuffer GBA; `--screenshot` lê a saída do renderer. Esses modos exigem limite de quadros e preservam a informação sobre dispositivos no JSON.

Em 2026-10-18, macOS Apple Silicon local:

- CTest desktop: 5/5 (inclui `sdl-identity`); modo portátil no host: 2/2 (sem SDL).
- ZIP original → pacote V1 → V2 → rollback/reparo: onze verificações de integração passaram, origem inalterada; relatório em `private/desktop-storage-integration-v1/integration-report.json`.
- V2 executou 1.800 quadros com GPU/Metal e CRT: 30,136871 s simulados / 30,141525 s ativos; 1.359.332 amostras não nulas; 5.783.528 bytes entregues ao stream; fila máxima 5.680 bytes e zero resets. Saída foi silenciada no dispositivo: isso comprova geração/envio, não audição.
- Captura com nearest compara os 1.843.200 bytes RGB da saída 960×640 à replicação 4x exata do framebuffer: zero diferenças, incluindo quatro bordas. O CRT sobre o mesmo framebuffer altera 1.686.011 bytes; a captura foi inspecionada. Não equivale a QA de outros GPUs, monitores ou filtros em todas as resoluções.
- UI: presença dos 24 acentos, reticências e travessões verificada na fonte; a captura `ui-fixed.png` foi inspecionada separadamente. O campo `ui_ptbr_glyphs_present` indica presença de glifos, não revisão visual de todas as telas.
- Medição warm de 1.800 quadros nearest com cache: `/usr/bin/time -lp` registrou 31,45 s de parede, 3,34 s user + 2,25 s sys, RSS máximo 141.705.216 bytes e footprint máximo 175.752.104 bytes. É um processo; não houve árvore de subprocessos do app. Inicialização/compilação Metal fica fora do tempo ativo do jogo. Não há baseline anterior equivalente nem medição de tokens/ensaio cold comparável.

Capturas, relatórios e dumps ficam em `private/reports/desktop-v1/`. São evidência local, fora da distribuição. Permanecem necessários QA com teclado/gamepad físico, audição/latência, desconexão de dispositivos, mudança de monitor/DPI/fullscreen, Windows real, Intel nativo e Android. Essas limitações impedem usar os ensaios como conclusão automática de todas as tarefas M4/M6/M7.

## Correspondência com as tarefas OpenSpec

Esta tabela avalia os critérios desta frente, antes de incorporar a QA visual do empacotamento executada pelo responsável principal. “Implementado” não fecha critérios de verificação pendentes.

| ID | Evidência já produzida | Critério restante / conclusão |
|---|---|---|
| 4.1 | Seletor local PT-BR, ZIP com escolha explícita, revisão/hash incorretos recusados, caminho UTF-8 testado no armazenamento e importação real do ZIP. | Falta exercitar seletor/cancelamento/caminho acentuado pelo teclado e gamepad físico na UI. Manter pendente. |
| 4.2 | Primeira instalação offline com rede negada por `sandbox-exec`; integração real de repetição, cache adulterado/reparado, atualização, histórico atômico e rollback nos dois sentidos; origem intacta. | Critérios locais implementados e verificados. Distribuição/plataformas continuam sujeitas a M6. |
| 4.3 | Ownership por âncora/identidade; cancelamentos antes do commit e resultado tardio coerente; rename recusado; conteúdo parcial, nome reutilizado e retry após falha de permissão; limite de escrita real do kernel preserva destino. | ENOSPC físico e interrupção real do processo durante todas as fases não foram executados; fixtures de recuperação não são prova de corte de energia. Manter pendente. |
| 4.4 | Escalas físicas 1x–6x e fit implementadas; limites cobertos; 4x Metal comparado byte a byte em toda a saída. | Falta matriz de DPI comum/Retina e todas as seis escalas em janela visível. Manter pendente. |
| 4.5 | Resize, fullscreen, fit, 3:2/esticado e recusa de escala excessiva implementados. | Falta sequência de transições, múltiplos monitores/DPI e inspeção visível. Manter pendente. |
| 4.6 | Nearest/linear/CRT implementados; nearest exato e CRT inspecionados no Metal; fallback software sem GPU executado, aviso persistente no JSON/UI. | Linear e variantes DXIL/SPIR-V ainda não tiveram inspeção visual real. Manter pendente na matriz multiplataforma. |
| 4.7 | Relógio GBA separado do renderer; mesmo número de quadros em 120 s sintéticos a 60/120/144/500 Hz; execução Metal de 1.800 quadros, tempos/filas registrados. | Falta validar monitores efetivos nessas frequências e pacing prolongado com vsync ligado/desligado. Manter pendente. |
| 4.8 | Stream 48 kHz estéreo, volume/mute, conversão SDL e fila limitada; 1.359.332 amostras não nulas enviadas ao dispositivo real. | Saída foi silenciada; não houve audição, troca/perda física de dispositivo nem suspensão real do host. Manter pendente. |
| 4.9 | Remapeamento, conflitos, deadzone, menu ImGui por teclado/gamepad, hotplug e limpeza de entrada por polling implementados. | Falta interação física e desconexão enquanto botão está pressionado. Manter pendente. |
| 4.10 | Config versão 1, backup, arquivo corrompido/versão desconhecida preservados, defaults e isolamento de saves testados. | Não há formato anterior a migrar; versões desconhecidas são recusadas/preservadas. Falta restauração/reabertura pelo menu real. Manter pendente. |
| 4.11 | Envelope de cartucho atômico, hash/compatibilidade, backup/recovery, import/export e perfis testados; M1 já possui save normal do jogo validado no harness. | Não confundir o teste M1 com uso da UI desktop; falta importar/reiniciar/exportar pela UI com save real e repetir sob troca de patch/incompatibilidade. Manter pendente. |
| 4.12 | A UI e `--help` dizem que savestates não são oferecidos; somente o harness diagnóstico tem checkpoints privados. Documentação mantém essa distinção. | Critério da opção “ausentes na v1” implementado/verificado. |
| 4.13 | Relatórios locais de tempo simulado/parede, áudio, pixel output e memória estão preservados; matriz técnica explicita desconhecidos. | QA integrada não concluiu Windows/Intel nativo nem dispositivos físicos. Manter marco aberto. |
| 7.1 | Core recebe ROM/save como buffers `std::vector`/`std::span`; BPS usa spans e offsets inteiros; VFiles de memória e SRAM foram exercitados em processo arm64 de ponteiro 64-bit. Modelo compila sem SDL. | Importador ZIP e persistência ainda expõem filesystem; entrada SAF/URI por stream e gravação transacional Android precisam de adaptador. Isso permanece aberto, sem converter URI em path de desktop. |
| 7.2 | Configuração NDK proposta abaixo; opções CMake removem UI/SDL em Android; build portátil no host e 2/2 CTest passaram. Busca pontual não encontrou toolchain NDK. | Conforme o texto da tarefa, a cobertura NDK está registrada como indisponível. Não há APK ou compilação NDK alegada. |

O ensaio offline usou, em diretório novo, `sandbox-exec -p '(version 1) (allow default) (deny network*)' build/khcom-desktop --headless --mute --frames 3 --rom ORIGINAL.gba --package PACOTE_V2/manifest.json ...`; terminou com status 0 e destino V2 correto. Relatórios `offline.json`/`offline.stderr` e `fallback.json` registram respectivamente ausência de dependência de rede e fallback de CRT para software. `--headless` não cobre GPU/áudio físicos.

### Configuração NDK proposta (não executada)

API mínima **proposta** 26, ABI arm64-v8a, com NDK instalado pelo proprietário no caminho indicado:

```sh
cmake -S . -B build-android-arm64 -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$ANDROID_NDK_HOME/build/cmake/android.toolchain.cmake" \
  -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-26 \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \
  -DKHCOM_BUILD_DESKTOP=OFF -DKHCOM_BUILD_DIAGNOSTIC=OFF
cmake --build build-android-arm64 --target khcom_core khcom_desktop_model --parallel
```

Em 2026-10-18, foram consultados apenas `ANDROID_NDK_HOME`, `ANDROID_NDK_ROOT`, `ANDROID_HOME`, `ANDROID_SDK_ROOT` e os diretórios padrão `~/Library/Android/sdk/ndk` e `~/Android/Sdk/ndk`. Nenhuma variável fornecia um caminho e nenhum dos diretórios padrão existia. Não houve download/instalação nem busca geral no disco. `private/reports/desktop-v1/ndk-presence.json` guarda a cobertura exata dessa consulta; um NDK em outro local permanece desconhecido. API 26 e permissões SAF/lifecycle deverão ser confirmadas na proposta Android antes de anunciar suporte.

`private/reports/desktop-v1/host-widths.txt` registra ponteiro/`size_t` de 8 bytes e o executável de teste arm64. Isso, junto do framebuffer/SRAM/input da fixture ARM autoral, estabelece execução do core e buffers em host 64-bit. Não prova um frontend Android, endianness diferente, todo acesso indireto possível do core nem leitura de URI SAF.

### Estabilidade da identidade SDL

O arquivo codeload fixado de SDL não contém `REVISION.txt`. A configuração oficial consultava o Git do repositório pai e anunciava uma revisão variável. `SDL_REVISION` agora recebe `sources.sdl.build_revision` (`SDL-3.4.18`) via cache CMake `FORCE`, antes de `FetchContent_MakeAvailable(sdl)`. Isso não modifica fontes SDL. O SHA-256 do archive continua sendo a identidade de aquisição; o override estabiliza a metadata da biblioteca. O teste `sdl-identity` compara `SDL_GetRevision()` ao valor do manifesto e `SDL_GetVersion()` ao header; o relatório e a aba Sobre também mostram a revisão. O configure e CTest finais registram `SDL-3.4.18`.

As medições longas/pixels preservadas precedem esse ajuste de metadata e a correção do commit de perfil da UI; não foram retroativamente reescritas. `final-identity-v2.json` verifica a inicialização do binário posterior, com a revisão SDL explícita. A captura `ui-corrente.png` documenta a escolha posterior do subtítulo **Corrente de Memórias**, mantendo **Kingdom Hearts**.

### Correções observadas durante QA dos pacotes

O primeiro `.app` visível foi amostrado pelo responsável principal enquanto a thread principal estava em `import_rom → read_file → fopen/open$NOCANCEL`, antes da ativação. O arquivo `private/reports/app-visible-hang-v1.txt` estabelece a posição do bloqueio; autorização TCC de Downloads é uma hipótese, não uma causa confirmada pelo stack. A aquisição/hash/ZIP e a enumeração do seletor agora executam em workers, mantendo o event loop e a mensagem de permissão disponíveis. Cancelar registra a intenção, mas não declara uma chamada de sistema bloqueada encerrada: o worker continua possuído até retornar. Na saída excepcional, o sinal de cancelamento é emitido antes do join e os objetos de cancelamento/progresso sobrevivem às futures. O ensaio `async-import-v2.json` confirma importação real sem erro no caminho local; a repetição visível do pacote é necessária para fechar o caso do sistema.

A primeira CI Windows apontou expansão da macro `max` em `std::max` através de headers mGBA/Windows. O contrato CMake de `khcom_core` agora propaga `NOMINMAX` e `WIN32_LEAN_AND_MEAN` para todos os consumidores próprios (core, modelo, aplicativo, harness e testes). O modelo não inclui mais `windows.h` desnecessariamente; os adaptadores Windows restantes protegem a definição local. Isso corrige a fronteira que produz a macro, em vez de contornar apenas uma chamada. CTest local 5/5 passou após a mudança; confirmação MSVC depende da nova execução CI, que não é substituída pelo teste macOS.
