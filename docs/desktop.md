# Uso da prévia desktop

Esta versão executa a ROM GBA no core mGBA e aplica o patch local. **A tradução
é parcial**: há pilotos de Sora, Riku, aviso APERTE INICIAR, menu de save e fontes
de créditos. O restante da localização continua em desenvolvimento.

Abra o `.app` no macOS ou o executável/instalador Windows quando disponível.
O jogo e o pacote de tradução não vêm no ZIP público. Na aba Jogo, selecione sua
ROM original `.gba` ou `.zip` e o `manifest.json` do pacote gerado localmente.
A revisão suportada é USA B8CE rev0, 32 MiB, SHA-256
`6f6e7b61bb7b6ef7e2bea6e9dd01e70570a715835cc3713abe86186fd2c4e28d`.
O arquivo original não é sobrescrito. ZIP com várias ROMs exige seleção explícita.

Use **Esc/F1** para abrir o menu e **Continuar jogo** para retornar. No controle,
o botão Guia abre o menu. Os botões e o navegador local também aceitam teclado
ou gamepad; não é necessário usar terminal para jogar com um pacote preparado.

| GBA | Teclado padrão | Controle padrão |
|---|---|---|
| A | X | Botão Sul |
| B | Z | Botão Leste |
| Start | Enter | Iniciar |
| Select | Backspace | Voltar |
| Direções | Setas | D-pad/analógico esquerdo |
| L | A | Ombro esquerdo |
| R | S | Ombro direito |

A aba Vídeo oferece escala física 1x–6x, ajustar à janela, proporção original
3:2 ou esticada, fullscreen, nearest, linear, CRT e vsync. Uma escala que não
cabe precisa ser informada pela interface. CRT depende do backend disponível;
um fallback deve permanecer visível. A simulação GBA mantém seu próprio relógio.
Áudio oferece volume/mute; Controles permite remapear teclado/gamepad e deadzone.
As configurações são salvas por usuário e podem voltar aos padrões pela aba Dados.

Há três perfis separados. Use o save do próprio jogo; o aplicativo persiste o
save de cartucho e mantém backup. Importação/exportação usa envelope `.khcs`
com identidade/compatibilidade. **Savestates não são oferecidos na interface**.
Os checkpoints do diagnóstico são ferramentas de investigação, não saves
intercambiáveis com versões do aplicativo. Não há multiplayer funcional na v1.

Dados por padrão:

- macOS: `~/Library/Application Support/KHCoM-PTBR/desktop/`.
- Windows: `%APPDATA%/KHCoM-PTBR/desktop/`.

A aba Dados mostra o caminho efetivo. Não apague essa pasta ao trocar o `.app`
ou atualizar o executável. Cache e save ficam fora da instalação; a versão
anterior do pacote pode ser reativada quando a verificação permitir. Falhas de
save/limpeza precisam permanecer informadas para permitir nova tentativa.

A prévia macOS tem selo ad-hoc local, sem Developer ID/notarização. Windows,
Mac Intel físico, versões mínimas e instalação limpa só serão anunciados como
verificados depois de seus testes. Veja `implementation.md`, `distribution.md`
e a cobertura por evidências em `coverage.md`.
