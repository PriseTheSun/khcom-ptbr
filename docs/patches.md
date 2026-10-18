# BPS: contrato e verificação

`tools/make_patch.py` gera um candidato determinístico BPS1 a partir da ROM
USA validada e de uma ROM derivada local. `tools/patch_rom.py` reaplica exigindo
os digests de origem, patch e destino do manifesto. Nenhuma saída substitui a
origem ou um arquivo existente.

```sh
.venv/bin/python tools/make_patch.py \
  --source private/rom/B8CE.gba --target private/rom/B8CE-roundtrip.gba \
  --out private/rom/identity.bps --manifest private/reports/identity-patch.json

.venv/bin/python tools/patch_rom.py \
  --source private/rom/B8CE.gba --patch private/rom/identity.bps \
  --manifest private/reports/identity-patch.json \
  --out private/rom/B8CE-bps-reapplied.gba
```

Esse exemplo é um patch de identidade, sem tradução. O gerador linear emite
SourceRead/TargetRead; o aplicador aceita também SourceCopy/TargetCopy, inclusive
deslocamentos negativos e cópias sobrepostas. CRCs cobrem origem, destino e
patch. O manifesto adiciona SHA-256; não constitui assinatura de autenticidade.

Limites do importador: imagens até 32 MiB, patch até 64 MiB, metadados até
64 KiB, 262.144 comandos e 65.536 registros de literais no relatório do gerador.
São orçamentos de memória/CPU/auditoria desta aplicação, não limites universais
do formato BPS. Erros identificam o limite atingido.

## Evidência

O formato segue a [especificação pública de byuu](https://github.com/Sir-Walrus/Flips/blob/ff216a75df0987047a67d7923567dc4482ce07ac/bps_spec.md).
Os testes incluem vetores escritos independentemente do encoder para todas
as operações, offsets negativos, cópia sobreposta, CRCs, bounds, SHA-256,
limites e casos pseudoaleatórios com seed fixa.

Floating IPS foi compilado separadamente no commit registrado em
`manifests/bps-verifier.json`. Ele aplicou nosso patch sintético; nosso aplicador
reconstruiu o destino de um patch delta gerado por ele. O programa é ferramenta
de verificação local, não é ligado ao runtime nem incluído no staging.

Na ROM local, o patch de identidade tem 29 bytes. Sua reaplicação confirmou
SHA-256 `6f6e7b61bb7b6ef7e2bea6e9dd01e70570a715835cc3713abe86186fd2c4e28d`.
Isso verifica a infraestrutura, sem alegar tradução ou compatibilidade de uma
ROM modificada em gameplay.

## Distribuição continua bloqueada por proveniência

O gerador lista cada intervalo literal com offset, tamanho e hash e marca
`distribution_approved: false`. Bytes originais recomprimidos podem aparecer
como literais de um patch; extensão `.bps` não comprova ausência de assets.
O auditor/receita de reconstrução local previsto na tarefa 2.13 ainda precisa
classificar todos esses intervalos. Nenhum script atual converte o relatório
em aprovação de release.
