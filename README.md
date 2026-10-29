# Receivables Registry (MVP)

Verificação independente de recebíveis: uma empresa carrega o seu ledger de faturas (CSV ou Excel), o motor
deteta duplicados e inconsistências, e o banco recebe um relatório (ecrã + PDF) que pode rever, contestar e arquivar.

Versão propositadamente simples. Stack: **FastAPI + SQLite** (backend) e **Next.js + TypeScript** (frontend).
A interface e o relatório estão em inglês (o público-alvo são bancos).

## Arrancar (2 terminais)

**1. Backend** (Python 3.10+)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt   # inclui pytest
uvicorn app.main:app --reload --port 8000
```

**2. Frontend** (Node 18.18+)

```bash
cd frontend
npm install
npm run dev
```

Abre http://localhost:3000. Na primeira execução são criadas 3 contas demo (password `demo1234`) e um engagement:
`bank@demo.com`, `client@demo.com`, `admin@demo.com`. Há botões na página de login para as preencher.

## Como testar (5 minutos)

1. Entra como **Company** (`client@demo.com`) e abre o engagement "Demo".
2. Carrega `backend/sample_data/sample_small_eu.csv` (300 linhas, formato europeu: `;`, `1.234,56`, `dd/mm/aaaa`).
   O mapeamento de colunas é sugerido automaticamente. Confirma a declaração e corre a verificação.
3. Resultado esperado: **Duplicates found**, com 2 duplicados exatos, 3 colisões de ID, 5 duplicados económicos
   e 6 tipos de problemas de qualidade de dados.
4. Sai e entra como **Bank** (`bank@demo.com`): vê o mesmo resultado, abre cada finding para ver as linhas,
   muda o estado (Open, Under review, Resolved, False positive), escreve uma nota e descarrega o **PDF**.
5. Abre "Audit trail" no fim da página: todas as ações ficam registadas numa cadeia de hashes.
6. Para testar com volume: `backend/sample_data/sample_10k.csv` (10.000 faturas com anomalias plantadas;
   o ficheiro `.expected.json` ao lado diz exatamente quais).

Podes também criar contas novas (Create account): um banco cria um engagement indicando o email da empresa,
e a empresa vê-o ao entrar com esse email.

## Testes automáticos

```bash
cd backend && pytest -q
```

Cobrem o parsing de montantes e datas, as 3 regras de deteção, a qualidade de dados, a API completa
(permissões, upload, revisão, PDF, auditoria) e o teste de sucesso de 10.000 faturas sintéticas
(as anomalias plantadas têm de ser encontradas exatamente, sem falsos positivos).

Gerar novos ficheiros sintéticos: `python -m scripts.make_synthetic --rows 10000 --out sample_data/novo.csv`
(`--eu` para formato europeu).

## O que o motor faz (regras determinísticas, sem ML)

| Regra | Definição |
|---|---|
| Duplicado exato | Mesmo ID de fatura, devedor, montante, moeda e datas, depois de normalizar (maiúsculas, pontuação, sufixos legais como Lda/SA/GmbH). Identificado por um hash SHA-256. |
| Colisão de ID | Mesmo ID de fatura (normalizado) com dados diferentes. |
| Duplicado económico (potencial) | IDs diferentes, mesmo devedor, montante e moeda, com datas de emissão a menos de 3 dias (`ECONOMIC_WINDOW_DAYS` em `engine.py`). |
| Qualidade de dados | Campos em falta, montante ilegível, zero ou negativo, datas inválidas, vencimento antes da emissão, data futura, moeda em falta. |

Veredicto: **Duplicates found** (duplicado exato ou colisão), **Potential duplicates** (só económicos) ou **No duplicates found**.
Pressupostos: datas lidas com o dia primeiro (31/12/2025); montantes aceitam `1.234,56` e `1,234.56`.

## Pôr online

Ver [DEPLOY.md](DEPLOY.md): GitHub + Vercel (frontend e backend) + Postgres, passo a passo.

## Estrutura

```
backend/app/engine.py     motor de verificação (funções puras, sem base de dados)
backend/app/main.py       API (auth, engagements, upload, findings, relatório, auditoria)
backend/app/audit.py      trilho de auditoria com cadeia de hashes
backend/app/report.py     relatório PDF
backend/tests/            testes
frontend/app/             páginas (login, lista de engagements, detalhe)
frontend/components/      upload e mapeamento, veredicto, findings, auditoria
```

## Simplificações desta versão (a mudar quando for a sério)

- **SQLite** por omissão em local; com `DATABASE_URL` aponta para PostgreSQL (suportado e testado). Ainda não há migrações (Alembic): as tabelas são criadas no arranque.
- Ficheiros guardados em disco (`backend/storage/`). Trocar por S3 em `app/storage.py`.
- Token de sessão em `localStorage` e `SECRET_KEY` de desenvolvimento: definir `SECRET_KEY` e usar cookies httpOnly em produção.
- Sem recuperação de password, verificação de email, nem convites. O banco liga-se à empresa só pelo email.
- Só deteta duplicados **dentro de cada ficheiro**. A deteção entre instituições (o registo propriamente dito) é a fase seguinte.
- O relatório só vale para o que foi submetido: não consegue detetar recebíveis omitidos (isto está dito no PDF).

## Variáveis de ambiente

Backend: `DATABASE_URL`, `SECRET_KEY`, `STORAGE_DIR`, `CORS_ORIGINS`, `SEED_DEMO` (0 para não criar contas demo), `DEMO_PASSWORD`, `ALLOW_REGISTRATION` (0 fecha o registo), `MAX_UPLOAD_MB`. Ver `backend/.env.example`.
Frontend: `NEXT_PUBLIC_API_URL` (por omissão `http://localhost:8000`, ver `.env.local.example`).
