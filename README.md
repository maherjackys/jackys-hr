# HR Policy Assistant — jackys-hr

Bilingual (Arabic / English) HR Policy chatbot built with Streamlit, LangChain, FAISS, and Groq.

## First launch / cold start

The embedding model (`intfloat/multilingual-e5-small`, ~470 MB) is downloaded from
Hugging Face on the very first boot. On Streamlit Community Cloud this takes
**2–4 minutes** before the app becomes interactive. Subsequent launches load the
cached model from disk in seconds.

Both FAISS indexes also rebuild on first launch (or whenever `index_version.txt`
is missing or outdated). Index build time depends on PDF count — typically under
60 seconds for the bundled documents.

## Knowledge sources

| Source | Documents folder | FAISS index |
|---|---|---|
| Company Policy | `hr_documents/` | `faiss_db/` |
| Dubai HR Policy | `dubai_hr_documents/` | `dubai_faiss_db/` |

Drop PDF files into the appropriate folder and redeploy — the index rebuilds automatically.

## Embedding model

`intfloat/multilingual-e5-small` — chosen for strong Arabic + English retrieval
within Streamlit Cloud's 1 GB RAM limit. e5 models require `"passage: "` prefix
on indexed text and `"query: "` prefix on search queries; both are applied
automatically in `core/rag_engine.py`.

## Secrets required (Streamlit Cloud)

```toml
GROQ_API_KEY    = "gsk_..."
SUPABASE_URL    = "https://xxxx.supabase.co"
SUPABASE_KEY    = "sb_secret_..."
```

## Running locally

```bash
pip install -r requirements.txt
streamlit run app.py
```
