# Smoke do instalador Windows

`tools/windows_install_smoke.ps1` implementa instalação por usuário, abertura
sem ROM, reinstalação do **mesmo instalador/mesma versão**, nova abertura e
desinstalação. Não é migração entre versões nem teste em máquina limpa. O
aplicativo C++ permanece inalterado. O ensaio não contém ROM, patch, credenciais
ou save válido do jogo.

## Execução no runner

Após produzir `dist/desktop/installer-build.json`, o instalador Inno 6.7.1 e o
payload auditado, executar em PowerShell 7 x64:

```powershell
./tools/windows_install_smoke.ps1 `
  -Installer ./dist/desktop/KHCoM-PTBR-windows-x64-setup.exe `
  -InstallerBuild ./dist/desktop/installer-build.json `
  -Payload ./dist/desktop/payload `
  -ReportPath ./dist/desktop/windows-install-smoke.json
```

O relatório deve ser novo e seu diretório pai deve existir. `-Python` aceita um
executável Python explícito, usado somente pela auditoria do CI, nunca como
dependência do aplicativo instalado. `-WorkRoot` opcional aceita **diretório
novo sob TEMP**, com espaço e caractere não ASCII; o padrão cria
`KHCoM smoke ação <UUID>`. A raiz é retida, com `ownership.json`, logs, recibos,
configuração, fixture e `result.json`. O caminho é impresso como
`KHCOM_SMOKE_ROOT=...` e consta no relatório copiado para `ReportPath`; o CI deve
reter essa árvore como artifact inclusive quando a etapa falha.

O script tem timeout por processo (120 segundos padrão). Timeout ou pipes de
descendente ainda abertos marcam conclusão não resolvida e impedem
desinstalação concorrente. Não se mata processo por PID encontrado, não se
adota instalação anterior e não se remove recursivamente a raiz retida. O
teardown do runner é a fronteira final nessa falha; isso não é anunciado como
cleanup concluído. Uma nova execução recebe outra raiz e **recusa** AppId
remanescente, preservando a evidência para análise.

## Critérios que o script verifica

1. Recusa o AppId `org.khcom.ptbr.experimental` já presente em HKCU/HKLM,
   views 32/64 bits. O SHA/tamanho do instalador devem coincidir com o recibo
   Inno 6.7.1 do CI. A raiz é criada exclusivamente e seu token é revalidado.
2. Audita o payload original e seus imports PE antes de executar instalação.
   Links/junções nos caminhos de entrada, raiz e instalação são recusados.
3. Instala silenciosamente em `Aplicativo ação`, sem reboot, sem fechar
   outros aplicativos e sem abertura automática. Registro deve ser HKCU e
   apontar exatamente à instalação possuída. Cada arquivo instalado coincide
   com o SHA/tamanho do manifesto original. `unins000.exe` e `unins000.dat`
   recebem identidade por hash, revalidada antes da atualização/desinstalação.
4. Inicia **o executável instalado** por 300 apresentações, `--hidden --mute`,
   sem ROM, com `--data-dir "Dados próprios"`. Somente app, System32 e Windows
   entram no PATH desse filho; o processo usa a raiz própria como CWD e não
   herda overrides nomeados de drivers SDL. Não se usa headless/dummy como
   fallback silencioso para obter sucesso.
5. Registra módulos observados por amostragem do processo possuído e seus
   hashes. Exige amostra e recusa módulos fora da instalação/Windows. O
   relatório do app deve ter 300 apresentações, zero frames de jogo, janela
   hidden, renderer presente, nenhuma ROM e nenhum erro de save.
6. Altera somente configuração própria (volume 37, escala 2) e cria um arquivo
   textual explicitamente sintético no caminho de saves. Reinstala o mesmo
   artefato e verifica preservação byte a byte antes da nova abertura; depois
   da abertura verifica as opções e o hash do fixture. Isto verifica retenção
   de arquivo, **não** validade CBOR/SRAM, save do jogo ou migração de schema.
7. Executa somente o desinstalador da instalação possuída, validando o caminho
   do registro e ambos os hashes antes de chamar. Registro e arquivos da
   instalação devem desaparecer; configuração e fixture permanecem intactos.
   Se uma etapa falha, tenta desinstalar apenas quando a identidade completa
   já foi estabelecida e não há processo não resolvido. Falha de cleanup é
   separada da falha principal; uma instalação parcial sem identidade é retida.

## Auditoria PE

`khcom/windows_pe.py` é o único parser desse ensaio. Lê DOS/PE, OptionalHeader,
seções, imports normais e delay-imports (RVA e VA antigos). Limita tamanho,
descritores e strings; recusa sobreposição, zero-fill sem bytes, diretório
truncado, nome com caminho, atributos desconhecidos e terminador ausente.
DLL local exige inventário do pacote e fechamento recursivo limitado. Imports
de VC redistributable/debug CRT falham mesmo se presentes no runner; `ucrtbase`
do sistema e API sets do Windows são tratados separadamente.

Resolução em System32 é evidência de caminho/hash, **não** assinatura Microsoft
nem origem de todos os componentes do SO. API sets são contratos do loader,
não arquivos inventados. A amostra de módulos acrescenta observação de startup;
não cobre todos os `LoadLibrary`, todos os caminhos do jogo, transições futuras
de driver, ou o fechamento de imports das DLLs do sistema.

O formato segue a [especificação PE da Microsoft](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format).
Os parâmetros seguem a documentação de [Setup](https://jrsoftware.org/ishelp/topic_setupcmdline.htm)
e [Uninstall](https://jrsoftware.org/ishelp/topic_uninstcmdline.htm) do Inno.
A identidade de registro segue [AppId](https://jrsoftware.org/ishelp/topic_setup_appid.htm).
Usa-se `ProcessStartInfo` com argumentos separados e PATH exato: a documentação
do [Start-Process](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.management/start-process)
explica que `-Environment PATH` pode acrescentar PATH do host, inadequado aqui.

## Evidência e pendências

No macOS foram executados os oito testes autorais de `test_windows_pe.py`,
incluindo malformed input, imports adiados ausentes, runtime de VC já presente
no host e conservação do contrato do produtor Inno. Esses testes não executam
o instalador nem provam sintaxe/execução do PowerShell. Não há `pwsh` local e
nenhum software foi instalado para simular Windows. O primeiro resultado real
deve vir do runner e será identificado pelo hash do script/instalador e relatório.

O snapshot CI `654f8e6`, run `39185744823`, é a referência já verde recebida para
o instalador anterior a este smoke, não uma alegação de execução deste script.
Permanecem em aberto para M6.2/M6.9: máquina limpa, instalador interativo/atalhos,
upgrade de uma versão anterior, perfil SDL padrão, importação/patch, gameplay,
save real, hardware de áudio/gamepad/vídeo e QA das campanhas. Assinatura do
instalador e tradução completa também não são demonstradas. `release_approved`
fica falso mesmo se o smoke passar.
