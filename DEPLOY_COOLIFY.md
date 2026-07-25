# 🚀 Deploy no Coolify — VisionAI Corporate LinkedIn Manager

## Serviço: `corp.visionai.com.br`

---

## Passo 1 — Criar o Serviço no Coolify

1. Abre o **painel Coolify** → **New Resource** → **Application**
2. Selecciona **"Deploy from a local path"** ou **"Git Repository"**
   - Se tiveres um repo GitHub: aponta para a pasta `corporate/`
   - Se for local: usa o Coolify CLI ou copia os ficheiros via SFTP/SSH para o servidor
3. **Dockerfile**: `Dockerfile` (está na raiz da pasta `corporate/`)
4. **Port**: `8001`

---

## Passo 2 — Variáveis de Ambiente no Coolify

No Coolify, vai a **Environment Variables** do serviço e adiciona:

| Variável | Valor |
|---|---|
| `LINKEDIN_CLIENT_ID` | `77ow1venbjuuqo` |
| `LINKEDIN_ACCESS_TOKEN` | (token corporativo do `.env`) |
| `LINKEDIN_REFRESH_TOKEN` | (refresh token corporativo do `.env`) |
| `LINKEDIN_ORG_ID` | `106355456` |
| `LINKEDIN_PERSON_URN` | `urn:li:person:7y8dp014B6` |
| `GEMINI_API_KEY` | (já configurada no Coolify) |
| `ADMIN_USER` | `hugo` |
| `ADMIN_PASS` | `VisionAI2026!` |
| `SESSION_SECRET` | `corp-visionai-2026-ultra` |
| `CORP_API_KEY` | `corp_visionai_2026` |
| `PORT` | `8001` |
| `PUBLIC_URL` | `https://corp.visionai.com.br` |

---

## Passo 3 — Domínio

1. Coolify → serviço → **Domains** → adiciona `corp.visionai.com.br`
2. Activa **HTTPS automático** (Let's Encrypt)
3. No teu DNS (Cloudflare/etc), cria um **CNAME** apontando `corp` → servidor Coolify

---

## Passo 4 — Deploy

Clica **Deploy** e aguarda. O Coolify vai:
1. Build do Docker image (instala dependências Python)
2. Arrancar o container na porta 8001
3. Configurar reverse proxy com HTTPS

---

## Verificação

Após deploy, testa:
```bash
curl https://corp.visionai.com.br/api/health
```

Resposta esperada:
```json
{
  "status": "ok",
  "service": "VisionAI Corporate LinkedIn Manager",
  "org_id": "106355456",
  "gemini_model": "gemini-2.5-flash"
}
```

---

## Acesso

URL: **https://corp.visionai.com.br**
Login: `hugo` / `VisionAI2026!`
