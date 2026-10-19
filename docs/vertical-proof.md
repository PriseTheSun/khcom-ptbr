# Prova vertical encerrada

A etapa 2.14 tem exemplos executados nos seis tipos exigidos. Cada receita
parte da ROM US original, preserva sua origem e tem destino/BPS identificados.
Isso permite iniciar lotes cujo consumidor esteja validado. Não libera todos
os catálogos, não conclui o restante de M2 e não representa tradução 100%.

| Superfície | Prova executada | Evidência e limites |
|---|---|---|
| Diálogo Sora | Frase traduzida, glifos/cores/posição confrontados com captura do jogo | `dialogue-probe.md`; prova conjunta Sora/Riku em `private/reports/vertical-v1/dialogue-pixels.json`: 36 glifos/964 pixels exatos. |
| Diálogo Riku | Entrada real no evento 149 e frase traduzida sem corte | `riku-dialogue-probe.md`; uma escrita diagnóstica de desbloqueio, não campanha concluída. |
| Menu | Salvar jogo?/Sim/Não realocados, ponteiros conferidos e save/reload; 24 acentos em baralhos | `matching.md`, `menu-probe.md`; atlas ASCII de debug permanece distinto e aberto. |
| Gráfico tiled | APERTE INICIAR nos cinco estados da animação, 57 capturas estáveis exatas | `title-graphic-probe.md`; compartilhamento interno preservado, demais recursos ainda abertos. |
| Crédito | VP, produção global em Sora e Riku; 23 bytes/86 pixels, 2.752 pixels exatos | `vertical-credit.md`; nomes preservados, inicialização diagnóstica explicitada. |
| Legenda/vídeo | Três legendas e Corrente de Memórias no raster da abertura | `movies.md`; 91 quadros editados exatos e 1.526 restantes preservados. Áudio/duração preservados; jitter até um frame do core registrado. |

Os patches de cada piloto foram aplicados pelo código do projeto e por Floating
IPS com destinos idênticos. Os acentos normal/destaque, menu selecionado/atenuado
e ambas as fontes dos créditos têm provas separadas em `font-runtime-coverage.md`.

`build_demo_package.py --recipe-version 4` combina sete produtores com ownership
exclusivo de cada byte alterado. A composição resultou no alvo
`eff9a5137c3847c279cf605c928f00f5ff513c34e9ca112fc332d62528c647e9`.
O BPS v2 tem 2.248.388 bytes e SHA-256
`2e95d746935260247d0930d298bd2c5a805e87a6a9f5b51f99017c16dcec3e2e`.
As provas individuais não são reatribuídas automaticamente a essa composição;
seu teste integrado e a auditoria da receita são registrados separadamente.

Permanecem abertos contratos de outros consumidores, pequena fonte de debug,
recompressão de gráficos tiled, traduções restantes, revisão linguística humana,
percursos completos e QA nas plataformas. Capturas ou acesso diagnóstico a um
final não são tratados como progressão normal até esse final.
