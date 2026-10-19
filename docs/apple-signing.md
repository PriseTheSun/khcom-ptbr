# Preparação de assinatura e notarização Apple

`tools/sign_macos.py` prepara uma **nova cópia** do payload macOS produzido por `package_desktop.py`. A origem permanece intacta. A assinatura não muda o estado experimental, não aprova release, não comprova tradução integral e não substitui QA do aplicativo. A tarefa 6.8 permanece aberta até execução real com Developer ID e notarização.

## Contrato de proveniência

A entrada é `PACOTE/payload/`, com seu `package-manifest.json` auditado. A ferramenta recusa arquivos extras, links, payload de jogo, digests divergentes e estruturas de bundle não suportadas. O fluxo atual aceita apps sem frameworks versionados e sem entitlements excepcionais: mGBA é interpretado e não solicita JIT nem desabilitação de library validation. Mudanças nesse contrato exigem revisão antes de assinatura.

A saída nova tem `payload/`, `provenance/` e, após conclusão, `result.json`. Proveniência fica fora do payload distribuído e fora do `.app` selado:

- `input-package-manifest.json` conserva os bytes exatos do manifesto de origem; `plan.json` registra seus hashes bruto/canônico, inventário e ordem dos alvos.
- `sources_sha256` e `binary_input_sha256` continuam sendo os hashes da compilação de entrada. O hash de fontes é conferido contra seu arquivo auditado. O hash do binário pré-empacotamento é carregado do manifesto de build: o binário original anterior ao selo ad-hoc não acompanha o payload e não é rederivado por este helper. Nenhum deles é substituído pelo hash do binário assinado.
- `signed-inventory.json` registra o inventário após assinatura e as mudanças antes/depois. `submit-attempt.json` vincula plano, inventário e ZIP enviado; `submission.json` guarda o UUID recebido da Apple.
- Depois de Accepted, stapling e verificações, `files[]` do manifesto final recebe os hashes/tamanhos dos arquivos finais. `apple_signing.changes` conserva os hashes anteriores e posteriores. Somente arquivos executáveis inventariados, regiões exatas de assinatura/ticket e a atualização declarada de `LEIA-ME.txt` podem mudar.
- A afirmação ad-hoc do `LEIA-ME.txt` **da cópia** é substituída após as verificações Apple. Avisos/licenças, SBOM e fontes continuam byte a byte iguais. O manifesto externo ao `.app` é refeito sem invalidar seu selo.
- O ZIP final é criado com `ditto` após stapling, reextraído e auditado; assinatura e ticket são revalidados na cópia extraída. `archive_sha256` e `output_manifest_sha256` são identidades de saída separadas.

Arquivos de plano/receipts são criados exclusivamente. Falhas preservam a pasta parcial para diagnóstico; não há limpeza por nome/PID nem sobrescrita da entrada. Um lock de lifetime do sistema impede execuções concorrentes no mesmo diretório. Resultado concluído não é reaberto para mutação.

## Uso local e CI

Não há instalação/importação de certificados nem criação de senhas/Keychains. O proprietário precisa provisionar previamente sua identidade **Developer ID Application**, chave privada e profile do `notarytool`. Referências podem vir de argumentos ou das três variáveis específicas; o script não persiste o ambiente:

| Argumento | Variável opcional | Conteúdo |
|---|---|---|
| `--identity` | `KHCOM_APPLE_IDENTITY_SHA1` | SHA-1 público exato da identidade, 40 caracteres hexadecimais. Não é senha. |
| `--profile` | `KHCOM_NOTARY_PROFILE` | Nome de profile já provisionado no Keychain. |
| `--keychain` | `KHCOM_APPLE_KEYCHAIN` | Caminho opcional de Keychain já provisionado/desbloqueado. |

A interface não aceita senha Apple ID, senha de certificado ou chave privada. Credenciais permanecem no Keychain; diagnósticos de subprocessos não são impressos sem filtro. Falhas expõem etapa, código de saída e hashes de stdout/stderr, sem copiar conteúdo de autenticação. Provisionamento de secrets do runner é responsabilidade do workflow/proprietário; não está automatizado neste helper.

```sh
# Read-only: inventário, ordem inside-out e prontidão; nenhum upload/escrita.
python tools/sign_macos.py --payload dist/PACOTE/payload --dry-run

# Read-only: exit 0 se apto a tentar; exit 3 se faltar ferramenta/identidade/profile.
python tools/sign_macos.py --readiness

# Somente com identidade/profile já provisionados nas variáveis acima:
python tools/sign_macos.py --payload dist/PACOTE/payload --out dist/ASSINATURA-NOVA --execute

# Consulta o mesmo UUID; não reenvia. Pode retornar pending.
python tools/sign_macos.py --resume dist/ASSINATURA-NOVA
```

A prontidão verifica ferramentas e a identidade exata em `security find-identity -v -p codesigning`. Presença do nome de profile **não comprova credenciais válidas**; `profile_credentials_verified` permanece false. Acesso à chave privada/serviço Apple só é comprovado pela execução real. Ferramentas são descobertas pelo `xcrun`, sem alterar `xcode-select`.

O primeiro comando de execução assina Mach-O e bundles individualmente, de dentro para fora, com hardened runtime, timestamp seguro e entitlements vazios; não usa `--deep` para assinar. Confere cada arquitetura para Developer ID, Team, runtime/timestamp e ausência de grants. `--deep --strict` é usado para **verificação**. O envio usa `notarytool submit --no-wait`, preservando o UUID. A retomada faz uma consulta `info`; somente `Accepted` permite stapling, `stapler validate` e `spctl` local.

Não há loop de polling. Timeout/erro depois do upload sem receipt é estado desconhecido: o script não reenvia. É preciso conciliar a submissão no histórico Apple antes de decidir outra operação. `Invalid`/`Rejected` não geram release nem ticket. Falhas de finalização podem ser retomadas pelo UUID existente; novos arquivos de transporte ficam em diretórios próprios, mantendo a tentativa anterior.

## O que foi realmente verificado

Em 2026-10-18 neste host:

- `xcrun` encontrou codesign, security, ditto, spctl, notarytool e stapler. `security find-identity -v -p codesigning` retornou **0 identidades válidas**.
- O dry-run do payload universal V3 auditou sua origem e planejou `KHCoM PT-BR.app/Contents/MacOS/khcom-desktop` seguido do bundle externo. O manifesto de entrada tinha SHA-256 `a9c1a7c76346b91332f5149bbbff9acd53b95cf9c993064fcc8d70c73e05735f`.
- Readiness retornou código 3, com `ready_to_attempt: false`; nenhuma assinatura Developer ID, submissão, notarização ou stapling foi executada.
- Quatorze testes de fixtures cobrem ordem nested, ausência de identidade, proveniência/hashes, status desconhecido/rejeitado, receipt ausente, recusa de alteração fora do contrato, lock concorrente, retry da finalização e proteção de diagnóstico de autenticação. O simulador não prova comportamento do serviço Apple nem validade de assinatura/ticket.

Evidências locais: `private/reports/apple-signing-v1/`. A task 6.8 continua aberta. Mesmo uma futura aprovação `spctl` local não comprova download limpo/Gatekeeper em outro Mac; esse campo permanece false no resultado. O ZIP final e o `.app` deverão passar essa QA real antes de distribuição.

## Referências primárias

A ordem inside-out e o uso de `--deep` só para verificação seguem [Apple TN2206](https://developer.apple.com/library/archive/technotes/tn2206/_index.html). O envio, conservação do UUID, uso de profile Keychain, stapling no `.app` e recriação do ZIP seguem [Customizing the notarization workflow](https://developer.apple.com/documentation/security/customizing-the-notarization-workflow). As opções também foram conferidas nos helps locais `xcrun notarytool submit --help`, `xcrun notarytool info --help`, `xcrun stapler --help` e `codesign --help`; as versões instaladas são as que executariam o plano.
