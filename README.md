# Rio Daily

Site e newsletter em inglês para turistas no Rio: notícias, zonas quentes e voos da Polônia.

## Rodar no computador

    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
    .venv/bin/python -m rio daily      # coleta tudo e gera site/
    .venv/bin/python -m rio demo       # gera site-demo/ com preços INVENTADOS
    .venv/bin/python -m rio pending    # o que espera aprovação
    .venv/bin/python -m rio approve ID

## Contas (no computador: arquivo `.env`; no GitHub: Settings > Secrets and variables > Actions)

| Segredo | Para quê |
|---|---|
| SERPAPI_KEY | voos (sem ele, nenhum preço aparece) |
| FOGOCRUZADO_EMAIL, FOGOCRUZADO_PASSWORD | tiroteios |
| GMAIL_USER, GMAIL_APP_PASSWORD, NEWSLETTER_TO | newsletter; comece com NEWSLETTER_TO = seu próprio email |

## Publicar

1. Crie um repositório **público** só com esta pasta e preencha `site` em `config.yaml`.
2. Em Settings > Pages, escolha **GitHub Actions**.
3. O agendamento fica **desligado** até você criar a variável `ENABLED` = `true` em Settings > Secrets and variables > Actions > Variables. Antes disso, rode manualmente em Actions.
4. Para aprovar: Actions > Rio Daily > Run workflow, com o ID mostrado no passo "Collect and build".

A lista de pendências e os dados ficam visíveis no repositório público. Confira a tradução com o original antes de aprovar.
Testes: `python -m pytest`
