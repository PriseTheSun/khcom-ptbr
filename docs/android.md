# Preparação Android

O alvo desta entrega é desktop. Não há APK nem integração Android concluída.
Esta lista vincula as integrações futuras aos contratos já existentes; portar
somente o executável desktop não implementa permissões, toque ou lifecycle.

| Contrato atual | Integração Android necessária | Critério de verificação |
|---|---|---|
| `Session::create` recebe ROM/save em bytes e `advance` recebe máscara GBA | JNI/SDL Activity fornece buffers; endereços GBA permanecem `uint32_t`, ponteiros de host nunca são convertidos em endereços do cartucho | Compilar arm64-v8a; executar fixture própria e ROM privada; testar limites e ownership dos buffers |
| Importação reconhece SHA-256, membro ZIP, orçamento e BPS | Seleção por Storage Access Framework; abrir `content://` pelo `ContentResolver` e copiar stream com orçamento para armazenamento privado | Documento renomeado, permissão revogada, ZIP ambíguo, stream truncado/cancelado e nenhum acesso amplo ao armazenamento |
| Cache e ativação por manifesto verificado | Cache em `filesDir`; tratar provider de documentos como stream, nunca como caminho POSIX | Reabrir após morte do processo em cada etapa; validar digest antes de ativar; preservar pacote anterior |
| Save de cartucho com envelope, versão, compatibilidade e backup | Exportar/importar via SAF; gravar em pausa e manter cópia privada | Processo encerrado durante gravação; restauração do backup; save desktop↔Android sem savestate |
| Relógio GBA separado da apresentação | Pausar em `onPause`, zerar atraso acumulado ao retornar; não executar centenas de frames para compensar suspensão | 60/90/120Hz, mudança de refresh e retorno após suspensão longa com duração simulada correta |
| Stream SDL com fila limitada | Rota Android/AAudio, foco de áudio, fones/Bluetooth, desconexão | Perda e recuperação de foco/dispositivo sem fila ilimitada, pitch alterado ou core acelerado |
| Teclado/gamepad e remapeamento | SDL gamepad Android, teclado externo e overlay de toque próprio | Hotplug, deadzone, multitouch, orientação, áreas seguras, botões liberados em perda de foco |
| Apresentação 240×160, nearest/linear/CRT e proporção | Backend GLES/Vulkan, shaders compatíveis, fallback informado | Cores/pixels, letterboxing, rotação, densidade e dispositivo sem shader |
| Configuração versionada e perfis | Armazenamento privado com migração e defaults | Atualização do APK preserva config/saves; desinstalação/exportação documentadas |

O Android deve reutilizar o parser BPS e as regras de identidade, compatibilidade
de save e limites. O seletor de arquivos, relógio de lifecycle e persistência em
`content://` pertencem ao adaptador Android. A camada de importação desktop
ainda aceita `std::filesystem::path`; isso não deve vazar para a API pública
Android. Extraia o parser ZIP para uma entrada de bytes/stream com tamanho
conhecido antes de ligar o SAF, mantendo as rejeições e escolha explícita de
membro já testadas no desktop.

Uma proposta Android futura deve fixar NDK/SDK/API mínima, implementar a Activity
e armazenamento por URI, definir layout tátil/acessibilidade, executar matriz
de dispositivos físicos e fornecer APK/AAB com assinatura do proprietário.
Não anunciar Android como plataforma disponível antes desses testes. O
toolchain NDK não foi instalado automaticamente neste projeto.

Referências oficiais para a futura integração:
[SAF](https://developer.android.com/training/data-storage/shared/documents-files),
[lifecycle](https://developer.android.com/guide/components/activities/activity-lifecycle),
[NDK com CMake](https://developer.android.com/ndk/guides/cmake),
[foco de áudio](https://developer.android.com/media/optimize/audio-focus).
