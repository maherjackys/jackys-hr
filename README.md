# HR Policy Assistant - jackys-hr

Bilingual Arabic/English HR policy assistant built with Streamlit, LangChain,
FAISS, FastEmbed, Groq, and Supabase.

## First Launch / Cold Start

The embedding model (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`)
is downloaded from Hugging Face on the first boot. On Streamlit Community Cloud
this can take a few minutes before the app becomes interactive. Subsequent
launches load the cached model from disk.

FAISS indexes rebuild on first launch, when `index_version.txt` is missing or
outdated, or when source documents change.

## Knowledge Sources

| Source | Documents folder | FAISS index |
|---|---|---|
| Company Policy | `hr_documents/` | `faiss_db/` |
| Dubai HR Policy | `dubai_hr_documents/` | `dubai_faiss_db/` |

Drop PDF, DOCX, TXT, or MD files into the appropriate folder and redeploy. The
index rebuilds automatically.

## Embedding Model

`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` is used through
FastEmbed for Arabic and English retrieval within Streamlit Cloud's 1 GB RAM
limit. It does not require e5-style `passage:` or `query:` prefixes.

## Secrets Required

For Streamlit Cloud, configure:

```toml
GROQ_API_KEY = "gsk_..."
SUPABASE_URL = "https://xxxx.supabase.co"
SUPABASE_KEY = "sb_secret_..."
```

Optional secrets:

```toml
APP_PASSWORD = "employee-app-password"
ADMIN_PASSWORD = "initial-admin-password"
ADMIN_RESET_CODE = "recovery-code"
```

## Running Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```
