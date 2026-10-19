# Fronteiras portáveis do runtime

O modelo compila com `KHCOM_BUILD_DESKTOP=OFF` e `KHCOM_BUILD_DIAGNOSTIC=OFF`, sem SDL, ImGui ou fonte de interface. Android força essas opções para OFF. As interfaces abaixo não dependem de caminhos Windows/macOS nem da presença de uma UI.

| Dono | Contrato | Limites e responsabilidade do adaptador |
|---|---|---|
| `Session` | `create(vector<uint8_t>, span<const uint8_t>)`, `save()`, `pixels()`, `audio_frame()` | Possui ROM imutável e core, usa VFiles em memória; não procura BIOS nem escreve arquivos implicitamente. ROM ≤32 MiB, save ≤128 KiB; perfil KHCoM usa SRAM 32 KiB. |
| `read_stream` | `istream&`, limite, tamanho esperado opcional → bytes/erro | Não busca/rewind/fecha o stream. Blocos de 64 KiB; limite máximo 128 MiB e byte sentinela no stack para detectar excesso. EOF normal, inclusive streams com exceptions, distinto de erro. Tamanho esperado detecta truncamento/crescimento. |
| `import_rom_bytes` / `import_rom_stream` | Buffer possuído ou stream → ROM validada ou escolhas ZIP | Mesmo parser/hash/revisão do wrapper `import_rom(path)`. ZIP em memória limitado; múltiplas ROMs exigem seleção. Nenhuma candidata alterada é aceita como origem. |
| `apply_bps` | Dois spans → buffer candidato | CRCs, tamanhos, contagem de comandos, relativos e hash posterior verificados. Offsets BPS usam `uint64_t`/`int64_t` com validação antes de indexação; não são ponteiros host. |
| `encode_save` / `decode_save` | Metadata de compatibilidade + span → envelope/bytes | Codec CBOR único, hash e identidade B8CE/compatibilidade; sem acesso ao filesystem. SRAM exatamente 32 KiB; envelope ≤64 KiB. |
| Adaptadores desktop | `read_file`, `import_rom`, `import_save`, `export_save`, `atomic_write` | Leitura de arquivo regular delega ao stream; import/export delegam aos codecs. Persistência transacional exige diretório local com hard link/rename atômico e lock de escritor. |

O limite de leitura é checado antes de consumir/expandir dados; a capacidade solicitada ao vetor não ultrapassa o limite. Um stream não seekable pode representar bytes obtidos por um futuro adaptador de file descriptor. A função não transforma `content://` em path e não cria um adaptador SAF. Permissões de URI, lifetime/revogação do FD, cancelamento de I/O e a transação no armazenamento interno Android continuam responsabilidades da futura plataforma. Exportação por DocumentsProvider não herda automaticamente atomicidade de rename/hard links do desktop.

## Tipos de endereço e verificação

A API do core expõe buffers e spans de tamanho `size_t`; não publica endereços emulados como ponteiros do host. O fixture ARM autoral serializa palavras `uint32_t` little endian na ROM e executa leitura de KEYINPUT, escrita de pixel e SRAM. O wrapper usa os acessos de memória do mGBA; não converte inteiros GBA em endereços nativos. O parser BPS usa aritmética de 64 bits validada e limita o destino a 32 MiB antes de indexar. Isso é uma revisão das fronteiras próprias, não uma auditoria exaustiva de cada cast do core upstream.

Em host Apple Silicon, `sizeof(void*)` e `sizeof(size_t)` são 8, `sizeof(int)` é 4 e `sizeof(long)` é 8, conforme `private/reports/desktop-v1/host-widths.txt`. `core-contracts` executou ROM autoral, framebuffer, input, persistência de SRAM em nova sessão e pareamento de checkpoint diagnóstico. Esse ensaio não contém assets/BIOS do jogo. O CI Windows anterior já executou esse contrato em LLP64; a suíte de recuperação do desktop foi a que apresentou falha separada de handle.

`desktop-contracts` agora verifica stream não seekable de 70.000 bytes com zero chamadas de seek, limite exato, zero bytes, EOF com exception mask, truncamento/crescimento, limite inválido recusado antes da leitura, failbit e erro de streambuf; um ZIP em stream conserva as duas opções de ROM. O codec de save roundtripa inteiramente em memória e recusa tamanho/compatibilidade inválidos. Esses são testes de adaptador e formato, não substitutos de SAF real.

Comandos executados após a refatoração:

```sh
cmake --build build --target khcom-desktop khcom-desktop-tests khcom-storage-integration --parallel 8
ctest --test-dir build --output-on-failure --timeout 120
cmake --build build-portable --target khcom-core-tests khcom-desktop-tests --parallel 8
ctest --test-dir build-portable --output-on-failure --timeout 120
```

Resultados locais: 5/5 desktop e 2/2 portátil. O contrato pedido em 7.1 tem cobertura de buffers/streams e host de 64 bits; NDK, ABI Android e dispositivos permanecem cobertura distinta, descrita em `desktop-runtime.md`. Não há APK alegado.
