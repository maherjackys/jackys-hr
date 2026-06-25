"""
RAG engine — multi-source edition.

Owns the FAISS vector index and the Groq LLM, exposes a single
`answer()` method. Supports two independent knowledge sources:
  - "company"  → hr_documents/  + faiss_db/
  - "dubai_hr" → dubai_hr_documents/ + dubai_faiss_db/

Key design choices:
1. FAISS instead of ChromaDB — avoids opentelemetry/protobuf conflicts
   on Streamlit Cloud's Python 3.14 runtime.
2. Separate FAISS indices per source — zero cross-contamination, each
   source answers only from its own documents.
3. The engine is initialised lazily per source inside Streamlit's
   @st.cache_resource, so switching sources does not reload the other.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ── Result dataclass ──────────────────────────────────────────────────────────
@dataclass
class AnswerResult:
    text: str
    status: str          # "ok" | "out_of_scope" | "no_answer" | "error"
    source_docs: list[str] | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────
def _load_pdf_texts(docs_dir: Path) -> list[str]:
    """Load and split all PDFs in *docs_dir* into text chunks."""
    try:
        from langchain_community.document_loaders import PyPDFLoader
        from langchain.text_splitter import RecursiveCharacterTextSplitter
    except ImportError as e:
        logger.error("Missing dependency: %s", e)
        return []

    pdf_files = list(docs_dir.glob("*.pdf"))
    if not pdf_files:
        return []

    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)
    texts: list[str] = []
    for pdf in pdf_files:
        try:
            loader = PyPDFLoader(str(pdf))
            docs   = loader.load()
            chunks = splitter.split_documents(docs)
            texts.extend(c.page_content for c in chunks if c.page_content.strip())
        except Exception:
            logger.exception("Failed to load PDF: %s", pdf.name)
    return texts


def format_history(messages: list[dict], turns: int) -> str:
    """Format the last *turns* Q&A pairs as plain text for the LLM prompt."""
    if not messages or turns <= 0:
        return ""
    # Skip the welcome message (index 0) and take the last N pairs
    pairs: list[str] = []
    relevant = [m for m in messages[1:] if m["role"] in ("user", "assistant")]
    for msg in relevant[-(turns * 2):]:
        prefix = "Human" if msg["role"] == "user" else "Assistant"
        pairs.append(f"{prefix}: {msg['content']}")
    return "\n".join(pairs)


# ── Main engine ───────────────────────────────────────────────────────────────
class RagEngine:
    """
    Retrieval-Augmented Generation engine for a single knowledge source.

    Instantiate one engine per source (company / dubai_hr).  Each engine
    maintains its own FAISS index and is isolated from the other source.
    """

    def __init__(self, settings, api_key: str, source: str = "company") -> None:
        self._settings  = settings
        self._api_key   = api_key
        self._source    = source
        self._docs_dir  = settings.docs_dir_for(source)
        self._db_dir    = settings.db_dir_for(source)
        self._index     = None
        self._llm       = None
        self._is_ready  = False

        self._build_index()
        self._init_llm()

    # ── Properties ────────────────────────────────────────────────────────────
    @property
    def is_ready(self) -> bool:
        return self._is_ready

    @property
    def source(self) -> str:
        return self._source

    # ── Index building ────────────────────────────────────────────────────────
    def _build_index(self) -> None:
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
            from langchain_community.vectorstores import FAISS

            embeddings = HuggingFaceEmbeddings(
                model_name=self._settings.embedding_model,
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True},
            )

            # Try to load existing index first
            index_file = self._db_dir / "index.faiss"
            if index_file.exists():
                try:
                    self._index = FAISS.load_local(
                        str(self._db_dir),
                        embeddings,
                        allow_dangerous_deserialization=True,
                    )
                    self._is_ready = True
                    logger.info("[%s] FAISS index loaded from disk.", self._source)
                    return
                except Exception:
                    logger.warning("[%s] Failed to load saved index — rebuilding.", self._source)

            # Build index from PDFs
            texts = _load_pdf_texts(self._docs_dir)
            if not texts:
                logger.warning("[%s] No PDF texts found — engine not ready.", self._source)
                return

            self._index = FAISS.from_texts(texts, embeddings)
            self._db_dir.mkdir(parents=True, exist_ok=True)
            self._index.save_local(str(self._db_dir))
            self._is_ready = True
            logger.info("[%s] FAISS index built and saved (%d chunks).", self._source, len(texts))

        except Exception:
            logger.exception("[%s] Index build failed.", self._source)

    # ── LLM init ─────────────────────────────────────────────────────────────
    def _init_llm(self) -> None:
        try:
            from langchain_groq import ChatGroq
            self._llm = ChatGroq(
                api_key=self._api_key,
                model=self._settings.llm_model,
                temperature=self._settings.llm_temperature,
                max_tokens=self._settings.llm_max_tokens,
            )
        except Exception:
            logger.exception("LLM init failed.")

    # ── Answer ────────────────────────────────────────────────────────────────
    def answer(self, query: str, history: str = "") -> AnswerResult:
        if not self._is_ready or self._index is None:
            return AnswerResult("", "no_answer")

        try:
            results = self._index.similarity_search_with_score(
                query, k=self._settings.retrieval_k
            )

            # Filter by similarity threshold (L2 distance — lower is better)
            relevant = [
                (doc, score)
                for doc, score in results
                if score <= self._settings.similarity_threshold
            ]

            if not relevant:
                return AnswerResult("", "out_of_scope")

            context = "\n\n---\n\n".join(doc.page_content for doc, _ in relevant)
            source_docs = [doc.metadata.get("source", "") for doc, _ in relevant]

            # Source-specific prompt framing
            if self._source == "dubai_hr":
                source_label = "Dubai HR policies and UAE Labor Law regulations"
            else:
                source_label = "the company's internal HR policies"

            prompt = f"""You are an expert HR Policy Assistant. Answer the following question based ONLY on {source_label} provided in the context below.

IMPORTANT RULES:
- Answer ONLY from the provided context. Do NOT use external knowledge.
- If the context does not contain enough information, say so clearly.
- Do NOT mix information from different sources.
- Be precise, professional, and cite relevant sections when possible.
- Respond in the same language as the question (Arabic or English).

{"Previous conversation:" + chr(10) + history if history else ""}

Context from {source_label}:
{context}

Question: {query}

Answer:"""

            if self._llm is None:
                return AnswerResult("", "error")

            from langchain_core.messages import HumanMessage
            response = self._llm.invoke([HumanMessage(content=prompt)])
            answer_text = response.content.strip()

            if not answer_text:
                return AnswerResult("", "no_answer")

            return AnswerResult(answer_text, "ok", source_docs)

        except Exception:
            logger.exception("[%s] Query failed.", self._source)
            return AnswerResult("", "error")
