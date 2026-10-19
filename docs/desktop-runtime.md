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

- CTest desktop: 4/4; modo portátil no host: 2/2 (sem SDL).
- ZIP original → pacote V1 → V2 → rollback/reparo: onze verificações de integração passaram, origem inalterada; relatório em `private/desktop-storage-integration-v1/integration-report.json`.
- V2 executou 1.800 quadros com GPU/Metal e CRT: 30,136871 s simulados / 30,141525 s ativos; 1.359.332 amostras não nulas; 5.783.528 bytes entregues ao stream; fila máxima 5.680 bytes e zero resets. Saída foi silenciada no dispositivo: isso comprova geração/envio, não audição.
- Captura com nearest compara os 1.843.200 bytes RGB da saída 960×640 à replicação 4x exata do framebuffer: zero diferenças, incluindo quatro bordas. O CRT sobre o mesmo framebuffer altera 1.686.011 bytes; a captura foi inspecionada. Não equivale a QA de outros GPUs, monitores ou filtros em todas as resoluções.
- UI: presença dos 24 acentos, reticências e travessões verificada na fonte; a captura `ui-fixed.png` foi inspecionada separadamente. O campo `ui_ptbr_glyphs_present` indica presença de glifos, não revisão visual de todas as telas.
- Medição warm de 1.800 quadros nearest com cache: `/usr/bin/time -lp` registrou 31,45 s de parede, 3,34 s user + 2,25 s sys, RSS máximo 141.705.216 bytes e footprint máximo 175.752.104 bytes. É um processo; não houve árvore de subprocessos do app. Inicialização/compilação Metal fica fora do tempo ativo do jogo. Não há baseline anterior equivalente nem medição de tokens/ensaio cold comparável.

Capturas, relatórios e dumps ficam em `private/reports/desktop-v1/`. São evidência local, fora da distribuição. Permanecem necessários QA com teclado/gamepad físico, audição/latência, desconexão de dispositivos, mudança de monitor/DPI/fullscreen, Windows real, Intel nativo e Android. Essas limitações impedem usar os ensaios como conclusão automática de todas as tarefas M4/M6/M7.
