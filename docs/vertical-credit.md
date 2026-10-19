# Crédito traduzido pelo pipeline público

O cabeçalho **“VP, produção global”** foi importado no catálogo UTF-8, validado
pelo perfil `staff-roll-ptbr-v1`, reinserido e observado nas duas variantes dos
créditos. Os nomes permaneceram intactos. A prova complementa o
[piloto de 24 acentos](credits-pilot.md), cujas linhas eram diagnósticas.

`credits_edit.build_credit_probe(data, *, rom_identity=None, fetch=False)`
retorna `(candidate, report)`. A receita chama os mesmos produtores
`extract_catalog` → `plan_translations` → `apply_translation_plan` da reinserção
de catálogos; não existe um segundo patcher textual. `build_profile` continua
dono somente das fontes. O resultado público reproduziu byte a byte a candidata
executada; uma nova chamada não é marcada como nova execução runtime.

O ID `us/staff_roll_script_text/gStaffRollVpGlobalProductionText` ocupa a linha
190. Prefixo `@`, destaque e terminador foram preservados: **23/23 bytes**, avanço
de **86 pixels**, X=77–163. A candidata muda 1.056 bytes em uma reserva textual
e nos quatro spans do perfil. Ponteiros, nomes, ícones e código são preservados.

| Artefato | SHA-256 |
|---|---|
| Original | `6f6e7b61bb7b6ef7e2bea6e9dd01e70570a715835cc3713abe86186fd2c4e28d` |
| Candidata | `050dc830d20a12edb2f2daa0ff6419ddb5bed57d62ef04089b929b0934d9fb7c` |

O BPS de **1.319 bytes**, reaplicado pelo projeto e por Floating IPS, produz a
candidata idêntica. Contém derivados gráficos do perfil e permanece privado;
essa igualdade não aprova distribuir seus literais.

Cada variante percorreu linhas 0–626, com 388 desenhos e 16.041 chamadas de glifo.
Ponteiros, bytes, fontes e posições coincidem com o parser da candidata. Os
**387 desenhos não editados** permanecem iguais ao baseline. As cinco seleções
de fonte e o fim da rolagem foram preservados.

As capturas nativas mostram a linha inteira, com `ç/ã`, sem corte ou sobreposição.
A comparação do retângulo completo 86×16 nas duas variantes confirmou **2.752
pixels exatos**, sem diferenças. X/avanços vêm do parser; as cores vêm da paleta
original e de `SrollTextSetColors(7,5,0,6)`. Y=81 foi medido pela única
correspondência exata do prefixo preservado `VP, ` antes de comparar a tradução
completa. Não houve ajuste por glifo, RGB aprendido, tolerância ou máscara.
Frame vazio e um pixel de tinta incorreto foram rejeitados antes de publicação.

A entrada usa as três escritas RAM de [credits-mode-entry.md](credits-mode-entry.md):
variante, argumento do filme e modo pendente. Title → Movie → StaffRoll e seu
Init real foram observados. ROM em arquivo/memória permaneceu igual e nenhum
save foi gravado no host. Isso não comprova conclusão normal das campanhas.

Artefatos: `private/reports/vertical-credit-v1/`, incluindo `catalog.json`,
`validation.json`, `build.json`, `bps.json`, `verification.json`,
`public-builder-equivalence.json`, `negative-cases-v2.json`, helper/lib hashes e
pastas `run-sora`/`run-riku`. A primeira fixture negativa de pixel usou cor errada
e falhou antes da mutação; ficou preservada e explicitamente substituída pelo
V2, que confirma a mutação antes da rejeição. A biblioteca usada é mGBA 0.10.5.

A inspeção foi feita pelo agente. Revisão linguística humana, demais créditos,
quatro espaçadores finais não alcançados e outras posições continuam pendentes.
