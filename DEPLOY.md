# Pôr online: GitHub + Vercel + Postgres

Arquitetura: **dois projetos Vercel** a partir do mesmo repositório GitHub (um para `frontend/`, outro para `backend/`)
e uma base de dados **PostgreSQL** gerida (Supabase ou Neon). Tempo estimado: 20 a 30 minutos.

```
Browser  ->  Vercel (frontend, Next.js)  ->  Vercel (backend, FastAPI)  ->  Postgres (Supabase/Neon)
```

## 1. Base de dados

Cria um projeto gratuito em [Supabase](https://supabase.com) ou [Neon](https://neon.tech) e copia a *connection string*
(formato `postgresql://...`). No Supabase usa a opção "Transaction pooler" (Project Settings > Database > Connection string),
que é a adequada para funções serverless. As tabelas são criadas automaticamente no primeiro pedido.

## 2. GitHub

Cria um repositório **privado** vazio em github.com (por exemplo `receivables-registry`) e, na pasta do projeto:

```bash
git init -b main
git add .
git commit -m "Receivables Registry MVP"
git remote add origin https://github.com/<o-teu-utilizador>/receivables-registry.git
git push -u origin main
```

O `.gitignore` já exclui a base de dados local, ficheiros carregados e `node_modules`. Não faças commit de passwords nem de `.env`.

## 3. Vercel: backend

1. vercel.com > **Add New > Project** > importa o repositório.
2. **Root Directory: `backend`**. O Vercel deteta o FastAPI sozinho (usa `backend/index.py`).
3. Em **Environment Variables** define:

| Variável | Valor |
|---|---|
| `DATABASE_URL` | a connection string do passo 1 |
| `SECRET_KEY` | uma string aleatória longa: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `SEED_DEMO` | `0` |
| `CORS_ORIGINS` | por agora `http://localhost:3000` (corriges no passo 5) |

4. **Deploy**. Abre `https://<backend>.vercel.app/health`: deve mostrar `{"ok":true}`.
   Se o deploy falhar com um `RuntimeError`, a mensagem diz que variável falta (a app recusa arrancar sem `SECRET_KEY`,
   sem Postgres, ou com contas demo públicas).

## 4. Vercel: frontend

1. **Add New > Project** > o mesmo repositório, desta vez com **Root Directory: `frontend`**.
2. Variável de ambiente: `NEXT_PUBLIC_API_URL` = URL do backend, **sem barra no fim** (`https://<backend>.vercel.app`).
3. **Deploy**. Esta é a morada que vais usar.

## 5. Ligar os dois

No projeto do backend: `CORS_ORIGINS` = URL do frontend (`https://<frontend>.vercel.app`) > **Redeploy**.
Sem isto o browser bloqueia os pedidos.

## 6. Usar

Abre o frontend > **Create account**: cria uma conta *Bank* e outra *Company* (com emails diferentes; podes usar
`o.teu.nome+banco@gmail.com` e `o.teu.nome+empresa@gmail.com`). O banco cria um engagement com o email da empresa;
depois entras como a empresa e carregas um ficheiro (há exemplos em `backend/sample_data/`).

Quando as tuas contas existirem, põe `ALLOW_REGISTRATION=0` no backend e faz redeploy, para ninguém mais se registar.

## Limites a conhecer

- **Ficheiros até 4,5 MB.** O Vercel rejeita pedidos maiores a uma função. Dá para cerca de 50 mil linhas de CSV;
  a app limita a 4 MB quando está no Vercel. Para ledgers maiores é preciso carregar direto para um armazenamento de
  ficheiros (Vercel Blob ou S3) e processar a partir daí. Se isto for um problema, o backend pode ir para Render, Railway
  ou Fly em vez do Vercel, sem mudar código.
- **O ficheiro original não fica guardado.** O disco do Vercel não persiste. As linhas processadas e o SHA-256 do ficheiro
  ficam na base de dados; os bytes originais não.
- **Plano gratuito do Vercel (Hobby): só uso pessoal e não comercial.** Serve para testares e mostrares o protótipo. Para
  clientes reais precisas do plano Pro. Confirma os termos atuais em vercel.com/docs/limits/fair-use-guidelines.
- Bases de dados gratuitas podem pausar por inatividade: o primeiro pedido depois de uma pausa demora mais.
- Dados de bancos e empresas: antes de usar com dados reais, é preciso reforçar a segurança (cookies httpOnly em vez de
  `localStorage`, recuperação de password, 2FA, backups, alojamento na UE e RGPD).
