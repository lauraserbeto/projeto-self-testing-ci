# Wallet API - Relatório técnico

## 1. Requisitos e critérios de aceite

API REST de carteira digital com conciliação entre saldos e lançamentos. Valores são inteiros em centavos de real; 1250 representa R$ 12,50. O cenário utiliza cadastros e gateway fictícios.

| ID | Requisito funcional e aceite | Verificação |
|---|---|---|
| RF01 | Criar conta com nome, documento único e saldo inicial não negativo; consultar por identificador. | Integração: cadastro, duplicidade e persistência; E2E: criação e consulta. |
| RF02 | Transferir valor positivo entre contas distintas, debitando e creditando atomicamente; recusar saldo insuficiente. | Unitários: cálculo e limites; integração: rollback e concorrência. |
| RF03 | Exigir `Idempotency-Key`: repetir chave e conteúdo devolve a mesma operação; conteúdo diferente retorna 409. | Integração: repetição, conflito, reinício do banco e 50 chamadas com a mesma chave. |
| RF04 | Consultar extrato por conta, datas inicial/final inclusivas e tipo `debit`/`credit`. | Integração: combinação de filtros; E2E: extratos de origem e destino. |
| RF05 | Notificar gateway antifraude por webhook, sem repetir o débito quando houver falha externa. | Mock: parâmetros e contagem; E2E: gateway HTTP fictício. |

| ID | Requisito não funcional |
|---|---|
| RNF01 | Preservar a soma dos saldos nas transferências e impedir saldo negativo sob concorrência. |
| RNF02 | Persistir contas, transferências, extrato e chaves; aplicar commit/rollback como unidade. Usar SQLite em memória nos testes de integração. |
| RNF03 | Atingir pelo menos 85% de linhas e 80% de branches, com limites independentes e falha automática abaixo de qualquer um deles. |
| RNF04 | Executar lint, testes e cobertura em push/PR; guardar logs e relatórios como artefatos. |
| RNF05 | Suportar teste com 50 requisições de transferência simultaneamente em andamento, medindo erros e latência. |
| RNF06 | Adotar branches curtas, commits convencionais e integração validada; exigir revisão e verificações na configuração remota. Atendimento parcial: não houve revisão por outro integrante. |

## 2. Arquitetura e contrato HTTP

Fluxo: `controllers → services → domain/repositories`. Os controladores validam entradas; o domínio calcula saldos sem dependências; o serviço coordena transferências; o repositório mantém SQLite e transações. As dependências de cadastro e antifraude são injetáveis.

O banco contém `accounts`, `transfers`, `entries` e `outbox`. Cada transferência grava dois lançamentos vinculados ao mesmo identificador. O saldo inicial positivo gera um crédito sem transferência associada. Assim, a soma dos créditos menos os débitos de cada conta corresponde ao seu saldo. Datas são gravadas em UTC.

`BEGIN IMMEDIATE`, `RLock` e restrições de unicidade protegem alterações concorrentes. O modo WAL é habilitado no banco em arquivo. A mesma transação grava saldos, lançamentos, chave idempotente e notificação pendente. Após o commit, o webhook é enviado com o identificador da transferência como chave. Falhas de comunicação preservam a pendência; repetir a requisição original tenta novamente sem movimentar saldo. Não há retentativa agendada. Uma interrupção entre o envio e a confirmação pode repetir o webhook; o gateway fictício deduplica os identificadores recebidos.

| Método e rota | Entrada principal | Resposta |
|---|---|---|
| `POST /accounts` | `name`, `document`, `initial_balance_cents` | 201, conta e saldo |
| `GET /accounts/{id}` | Identificador na rota | 200, conta e saldo |
| `POST /transfers` | `source`, `target`, `amount_cents`; cabeçalho `Idempotency-Key` | 201, operação; repetição retorna a mesma operação |
| `GET /accounts/{id}/statement` | Opcionais: `start`, `end` (`AAAA-MM-DD`), `type` | 200, lançamentos em ordem de inclusão |
| `GET /health` | Sem corpo | 200, estado da API |

Erros: 400 para regras inválidas, 404 para conta inexistente, 409 para saldo insuficiente/duplicidade/conflito e 422 para entrada incompatível ou cadastro recusado. Cada valor de entrada admite até `10^12` centavos. O cadastro padrão aceita documentos fictícios, exceto `blocked`; não representa validação de CPF nem serviço bancário real.

## 3. Testes e evidências

Pirâmide final: **34 unitários, 22 de integração e 7 E2E; 63 testes aprovados**. Os E2E iniciam a API e o gateway em portas locais e usam requisições HTTP reais. Os testes de integração empregam SQLite em memória; um teste adicional reabre um banco em arquivo para verificar persistência e idempotência.

O stub cadastral fornece respostas fixas para `doc-a`, `doc-b` e `doc-c`. O mock do gateway verifica `assert_called_once_with`, número de chamadas e ausência de envio em operações recusadas. Outro teste confere JSON, URL, cabeçalho e timeout do adaptador HTTP. Uma falha induzida durante a gravação do crédito comprova rollback dos saldos, transferência e outbox.

O ciclo TDD está preservado no Git e em `artifacts/tdd-*.log`:

| Etapa | Commit | Evidência |
|---|---|---|
| Red | `70d1114` | 18 testes falham com regras ainda não implementadas. |
| Green | `eaf18fc` | Os mesmos 18 testes passam após implementar as regras. |
| Refactor | `f5b3147` | Limites centralizados e casos de fronteira ampliados: 28 testes passam. |

Resultado final de Coverage.py: **100% de linhas e 100% de branches**, sem exclusões de código de produção. `artifacts/coverage.json`, `coverage.xml`, `tests.xml` e logs permitem auditoria; a execução também produz HTML. O gate calcula separadamente as duas taxas e tem testes para os limites exatos e resultados abaixo deles.

## 4. Integração contínua e versionamento

O workflow `.github/workflows/ci.yml` monitora pushes em `main`, `feat/**` e `fix/**`, além de PRs para `main`. O job `quality` executa Ruff, formatação, as três suítes e o gate; `load` executa a carga após aprovação de `quality`. Logs e cobertura são publicados mesmo quando uma etapa falha, com retenção de 14 dias.

A estratégia adotada é Trunk-Based Development com as branches curtas `feat/regras-financeiras` e `feat/api-ci`. O primeiro merge local integra o ciclo TDD após 28 testes aprovados; o segundo reúne API, integração, E2E, CI e carga após validação completa. Ambos usam `--no-ff`, preservando a evidência no histórico. A publicação da implementação está na branch `feat/entrega-api`, proposta para integração em `main` por pull request. O commit inicial contém somente a configuração das ferramentas. Consulte `git log --graph --oneline --all`.

**Evidências remotas verificadas em 18/11/2026:**

| Item | Evidência e situação |
|---|---|
| Repositório | [lauraserbeto/projeto-self-testing-ci](https://github.com/lauraserbeto/projeto-self-testing-ci) |
| Integração contínua | [Execução 44305272010](https://github.com/lauraserbeto/projeto-self-testing-ci/actions/runs/44305272010), commit `a6ac870`: jobs `quality` e `load` concluídos com sucesso. |
| Pull request | [PR #1](https://github.com/lauraserbeto/projeto-self-testing-ci/pull/1), de `feat/entrega-api` para `main`: aberto, sem aprovação de revisão obrigatória. |
| Proteção de `main` | Ativada: checks `quality` e `load` obrigatórios e branch atualizada antes do merge. Aprovações obrigatórias: zero. Regras aplicadas aos administradores; force-push e exclusão bloqueados. |

A proteção foi conferida pela API do GitHub e corresponde a `.github/main-protection.json`. Por indisponibilidade de outro integrante para revisar, a exigência de aprovação foi retirada, mantendo os checks obrigatórios. Não houve revisão por outra pessoa; portanto, o critério de PR revisado do enunciado não foi atendido. O merge depende dos checks da última atualização passarem. A implementação ainda não foi integrada à `main` remota.

## 5. Desempenho e resiliência

Medição local de 18/11/2026, Windows, Python 3.12.14, SQLite em arquivo e gateway HTTP fictício, executada com Locust por 20 segundos:

| Métrica do endpoint de transferência | Resultado |
|---|---:|
| Usuários / pico de requisições em andamento | 50 / 50 |
| Transferências concluídas | 935 |
| Falhas / taxa de erro | 0 / 0% |
| Latência média | 1.028,14 ms |
| Percentil 95 aproximado | 2.100 ms |

O preparo de 100 contas é separado das métricas de transferência. Uma barreira libera a carga após o cadastro dos 50 usuários; um contador registra as requisições sobrepostas. O script falha se não atingir 50, não produzir transferências ou registrar falhas. Evidências: `artifacts/load-summary.json`, CSVs e `load.log`.

Não houve travamento no cenário medido. A serialização das escritas e o envio síncrono ao gateway limitam a vazão; as medições locais não representam capacidade de produção. Os testes concorrentes também confirmaram uma única operação para 50 repetições da mesma chave e apenas 10 débitos de 1.000 centavos quando 50 chamadas disputaram um saldo de 10.000.

## 6. Execução

Requer Python 3.12. Execute dentro desta pasta, usando o Python do ambiente virtual:

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/verify.py
python scripts/run_load.py
```

Para uso manual, inicie os dois processos em terminais separados:

```sh
python -m uvicorn scripts.fake_gateway:app --port 8001
python -m uvicorn src.main:app --port 8000
```

A documentação interativa fica em `http://127.0.0.1:8000/docs`. `.env.example` documenta as variáveis opcionais `DATABASE_PATH`, `ANTIFRAUD_URL` e `ANTIFRAUD_TIMEOUT`; os valores padrão já permitem a execução acima. Para alterá-los, defina as variáveis no shell. Os scripts de teste e carga administram os próprios servidores e bancos isolados.
