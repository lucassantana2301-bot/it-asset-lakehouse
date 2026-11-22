# Como contribuir

Obrigado pelo interesse! Este guia descreve o fluxo usado no projeto.

## Ambiente

Pré-requisitos: Python 3.12+ e [uv](https://docs.astral.sh/uv/); Terraform 1.9+ só para a pasta infra/.

```bash
uv sync
uv run lakehouse run          # gera, ingere, roda o dbt e grava site/index.html
uv run dagster dev            # interface do Dagster em http://localhost:3000
```

## Fluxo de trabalho

1. Abra (ou escolha) uma issue descrevendo o problema. Mudanças grandes merecem discussão antes do código.
2. Crie uma branch a partir de `main` com prefixo do tipo: `feat/`, `fix/`, `docs/`, `refactor/`, `ci/`, `chore/`.
3. Faça commits pequenos no padrão [Conventional Commits](https://www.conventionalcommits.org/pt-br/v1.0.0/):
   `feat(api): adiciona filtro por região`, `fix(ingest): trata BOM no CSV`.
4. Rode as verificações antes de abrir o PR:

   ```bash
   uv run ruff check .
   uv run ruff format --check .
   uv run mypy
   uv run pytest --cov
   (cd infra/terraform && terraform fmt -check && terraform validate)
   ```

5. Abra o PR usando o template. O CI precisa estar verde e o PR é integrado com **squash merge**.

## Padrões

- Testes acompanham toda mudança de comportamento; bugs corrigidos ganham um teste de regressão.
- Decisões de arquitetura relevantes viram um ADR em `docs/adr/`.
- Nunca commite segredos, `.env` ou dados reais (billing, clientes, documentos internos).
- Versionamento segue [SemVer](https://semver.org/lang/pt-BR/) e o histórico fica no [CHANGELOG](CHANGELOG.md).

## Release

1. Em um PR, mova os itens de `[Não lançado]` do `CHANGELOG.md` para a nova versão e atualize
   a versão do projeto (`__version__` em `src/lakehouse/__init__.py`).
2. Ao integrar o PR na `main`, o workflow `release.yml` percebe a versão nova, valida o código,
   publica os artefatos e cria a tag `vX.Y.Z` e a release com as notas do CHANGELOG.
3. Também é possível disparar pela aba Actions (`workflow_dispatch`) ou enviando a tag à mão.
