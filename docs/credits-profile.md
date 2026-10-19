# Perfil de fontes PT-BR dos créditos

`tools/prepare_credits.py` reconstrói as duas fontes de créditos a partir da ROM
USA validada. O código contém a receita dos acentos; os pixels das letras-base
são lidos da cópia do usuário. Não inclui bitmaps originais no pacote de fontes.

```sh
.venv/bin/python tools/prepare_credits.py \
  --rom "/caminho/sua-copia.zip" --out private/credits-profile
```

O comando gera uma candidata **apenas com fontes**, dois atlas PNG, uma `.tbl`
UTF-8 e `report.json`. Não traduz nem substitui nenhuma linha do roteiro.
Requer o snapshot upstream fixado; `--fetch-upstream` obtém esses arquivos
quando ausentes. `--member` conserva a seleção explícita de ROM em um ZIP.
O destino deve ser novo e ficar em `private/`; falhas deixam as saídas parciais
identificáveis, sem sobrescrever arquivos existentes. O relatório é publicado
por último e identifica a entrada, os spans alterados e seus hashes.

## Contrato do codec

O perfil `staff-roll-ptbr-v1` aplica-se exclusivamente ao domínio
`staff_roll_script_text` com as fontes reconstruídas. Mapeia os 24 acentos
`áéíóúâêôãõçàÁÉÍÓÚÂÊÔÃÕÇÀ` aos bytes `82A0..82B7`, em ordem de arquivo,
que o renderer já encaminha aos índices 210–233. Mantém ASCII imprimível e
os caracteres largos `”` e `＠` encontrados no inventário US. Não redefine
CP932; por exemplo, `82A0` representa `á` neste perfil, e não `あ`.

`khcom.credits_profile.encode_line` recebe uma linha Unicode NFC **sem o token
`{END}`**, preserva os prefixos de roteiro e acrescenta um único NUL.
`decode_line` devolve essa mesma representação. A tabela usa `00={END}` como
notação editorial do terminador. Caractere desconhecido, código truncado,
NUL embutido, Unicode decomposto e excesso do limite editorial são erros
explícitos; não há substituição silenciosa nem fallback CP932.

O catálogo geral mantém sua origem e seu codec original. A reinserção genérica
continua bloqueada para traduções sem referências/layout comprovados. A opção
`--profile staff-roll-ptbr-v1` em `validate_localization.py` e `reinsert.py`
seleciona o [contrato por ocorrência](validation.md) de créditos; permite
candidatas em reservas fixas somente onde as verificações descritas passam. Codificar
uma linha com este perfil não aprova comandos, posição, largura ou referências;
esses contratos continuam pertencendo ao parser e aos validadores de contexto.

## Verificação realizada

A execução pública, em `private/credits-profile-v2/`, produziu:

- **1.041 bytes alterados**, todos nas quatro regiões de fontes/larguras,
  cuja capacidade total é de 1.200 bytes. ROM continua com 32 MiB.
- **255 itens originais** recodificados exatamente e **631 linhas** com os
  mesmos comandos e métricas estáticas. Pixels fora dos índices 210–233,
  tabelas de mapeamento, ponteiros e texto permaneceram idênticos.
- **48 glifos e avanços** iguais aos do [piloto V2](credits-pilot.md), nos
  dois atlas. Acrescentar apenas suas quatro linhas diagnósticas reproduziu
  byte a byte a candidata já exercitada em Sora e Riku; não houve nova execução
  runtime nessa comparação.
- BPS de **1.296 bytes**, reaplicado pelo aplicador próprio e Floating IPS,
  com destino idêntico. Duas reconstruções produziram a mesma candidata.
- Destino existente rejeitado antes de leitura da ROM ou alteração dos arquivos.

SHA-256 da candidata somente com fontes:
`e38fbd474a20fd1c0ad974e740ed9f9fe3d3a1823489ae1df10d2033aabf40b3`.
A equivalência completa, hashes dos scripts e identidades das evidências estão
em `private/credits-profile-v2/equivalence.json`. Os oito testes públicos do
perfil usam células autorais e cobrem codificação, limites, recusa de entradas
inválidas, forma do til, cedilha, preservação da base e ausência de mutação.

Uma execução com dependências já em cache mediu 1,51 s de parede, 1,43 s de CPU
usuário e 0,05 s de sistema; RSS máximo de 281.673.728 bytes. O processo não
lançou filhos. Não houve comparação cold/warm controlada nem medição de tokens.

O reuso dos índices continua limitado à revisão US e à investigação documentada
dos consumidores. A tipografia de 8 pixels é experimental, sobretudo as
maiúsculas compactadas. Atlas, candidata e BPS contêm derivados da ROM do usuário
e continuam privados. Este resultado não fecha os requisitos gerais de fontes,
prova vertical, auditoria de distribuição nem tradução dos créditos.
