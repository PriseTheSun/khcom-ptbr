# Persistência e recuperação: evidência local

Em 2026-10-18, os ensaios abaixo usaram diretórios privados próprios em macOS/APFS. A origem e relatórios anteriores foram preservados. O desktop permanece experimental; estes testes não equivalem a tradução completa ou tolerância a qualquer falha de hardware.

## Disco cheio real

Foi criada uma imagem APFS de 128 MiB e instalado o pacote V1. Um arquivo de preenchimento pertencente ao ensaio consumiu 95.420.416 bytes até o sistema devolver **errno 28 / ENOSPC**. Com o volume cheio, a atualização para V2 terminou com código 1, `Gravação incompleta`. O conteúdo de `active.json` permaneceu idêntico, SHA-256 `648d27533e4e274a459b5c6ce2526cadf04986d1bced6ebd51aa49b6746a7435`. Depois de remover apenas o preenchimento do ensaio, o retry ativou o destino V2 correto.

Isso exercita ENOSPC de um filesystem real limitado; não houve preenchimento do disco de trabalho do usuário. A imagem foi desmontada após revalidar sua identidade em `hdiutil info`. A imagem privada contém cache da ROM e não pode integrar fontes/artefatos públicos. Evidência: `private/reports/desktop-lifecycle-v1/{capacity,full-disk-result,retry,cleanup}.json`, logs de criação/montagem/desmontagem. A primeira tentativa de formato da imagem falhou; foi preservada e não conta como execução de capacidade.

## Interrupção real antes do commit

O helper privado `private/reports/desktop-lifecycle-v1/crash-recovery.py` criou um processo filho do aplicativo, instalado V1 e iniciando V2. Ao observar journal, âncora e temporário com a mesma identidade de arquivo, suspendeu **o filho que possuía**, verificou `active.json` anterior e terminou esse processo com SIGKILL. Não seleciona processos por nome/PID histórico.

Dois ensaios preservados:

| Evidência privada | Bytes observados no temporário | Resultado após reinício |
|---|---:|---|
| `desktop-lifecycle-v1/crash-recovery.json` | 0 | V1 permaneceu ativa; temporário, âncora e journal reconhecidos foram removidos. |
| `desktop-lifecycle-after-payload-v1/crash-recovery.json` | 33.554.432 | V1 permaneceu ativa; mesma recuperação. |

O segundo instante fica após a escrita do payload e antes de seu commit; não identifica exatamente o limite interno de `fsync`. Ambos os filhos encerraram com código −9 e foram coletados. O binário usado tinha SHA-256 `14d280c8747b32262128ab3cf605e7df5ad94454b09a9b99ab69aca719fafdda`. Isso não simula corte de energia, crash do kernel nem todos os possíveis instantes de I/O. Não reatribuímos essa evidência a builds posteriores.

## Cancelamento, cleanup e retry

`khcom-storage-integration` verifica usando a ROM e dois pacotes reais, em diretório novo:

```sh
build/khcom-storage-integration ORIGINAL.gba PACOTE_V1/manifest.json \
  PACOTE_V2/manifest.json DIRETORIO_NOVO
```

Há cancelamento antes do trabalho e nas fronteiras patch/cache/ativação. Até o commit, o ponteiro anterior permanece idêntico. Cancelamento observado no callback de conclusão depois do commit retorna sucesso e mantém o histórico correto. O resultado completo está em `private/desktop-storage-integration-v4/integration-report.json` (a entrada deste ensaio foi o GBA; o campo legado `source_archive_sha256` contém o hash desse arquivo de entrada). O ensaio anterior V1 usou o ZIP. Nenhum deles afirma gameplay.

`desktop-contracts` cobre rename recusado, identidade de temporário trocada, ownership malformado preservado, payload parcial, commit já concluído e múltiplos registros. No POSIX também provoca falha real de escrita por `RLIMIT_FSIZE` e falha de cleanup por permissão; restauração da permissão permite retry. A recuperação fecha o journal antes de removê-lo, necessário em Windows, e primeiro enumera os registros para não mutar o diretório em iteração. A CI Windows anterior identificou a falha de handle; nova execução deve confirmar a correção nesse host. Falhas mantêm nomes/motivos nos diagnósticos, não são convertidas em sucesso.

## Configuração

O aplicativo real foi iniciado com JSON malformado e, separadamente, `schema_version: 99`. Cada entrada foi preservada em um `.invalid-*`, o app persistiu defaults schema 1 e os hashes de `active.json`/saves permaneceram iguais. Evidência: `private/reports/desktop-lifecycle-v1/config-recovery.json` e relatórios/stdout/stderr individuais. A suíte cobre também roundtrip de opções e caminhos UTF-8.

Não existe schema anterior lançado para migrar. A política de versão desconhecida preserva os dados e aplica padrões, sem anunciar uma migração realizada. O ensaio de restauração **pelo menu visível**, seguido de reabertura, continua necessário para completar literalmente 4.10.

## Limites de encerramento

Os critérios locais de 4.3 foram exercitados por cancelamento, ENOSPC, rename, cleanup e retry; o acompanhamento Windows permanece explícito. Um processo morto antes de registrar ownership pode deixar um órfão não comprovado, que não é apagado por heurística. Chamada de sistema bloqueada durante aquisição não é declarada cancelada enquanto o worker não retorna; o app conserva ownership da future. Não houve teste de falha física de armazenamento ou suspensão do sistema no meio do commit.
