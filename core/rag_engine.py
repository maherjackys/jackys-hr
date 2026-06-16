"""
RAG engine.

Owns the FAISS vector index and the Groq LLM, and exposes a single
`answer()` method. Key design choices, explained:

1. FAISS instead of ChromaDB — chromadb pulls in opentelemetry/protobuf,
   which currently breaks on Streamlit Cloud's Python 3.14 runtime.
   FAISS has no such conflicts and is lighter for a small/medium
   document set like a company's HR policies.

2. A SINGLE retrieval call per question — the original code searched
   the vector store twice (once with k=1 to check the similarity
   threshold, once more inside the chain with k=3). This version
   retrieves once with k=3 and reuses the same results for both the
   threshold check and the answer context, roughly halving retrieval
   latency per question.

3. Lightweight conversation memory — the last few turns are passed to
   the LLM as context so it can handle natural follow-up phrasing
   ("and what about sick leave?"). Retrieval itself still searches
   using only the current question; this keeps the system simple and
   accurate for FAQ-style documents. If true conversational retrieval
   (rewriting the query based on history before searching) is needed
   later, that is the next extension point — not implemented here to
   avoid adding complexity the current use case doesn't need.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_community.vectorstores import FAISS
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import Settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a smart HR policy assistant.\n"
    "CRITICAL: Reply in the SAME language as the user's question.\n"
    "  - Arabic question -> Arabic answer\n"
    "  - English question -> English answer\n"
    "Answer ONLY using the provided documents. Be accurate and concise.\n"
    "If the answer is not clearly in the documents, reply with exactly: NOT_FOUND\n\n"
    "Recent conversation (for context only — do not repeat it back):\n{history}\n\n"
    "Documents:\n{context}"
)


@dataclass
class RagResult:
    text: str
    top_score: float | None
    status: str  # "ok" | "out_of_scope" | "no_answer"


def format_history(messages: list[dict], max_turns: int) -> str:
    """Render the last `max_turns` user/assistant exchanges as plain text."""
    relevant = messages[-(max_turns * 2):] if messages else []
    lines = [f"{m['role']}: {m['content']}" for m in relevant if m.get("role") in ("user", "assistant")]
    return "\n".join(lines) if lines else "(no previous turns)"


class RagEngine:
    """Owns the vectorstore + LLM and answers queries with retry handling."""

    def __init__(self, settings: Settings, api_key: str):
        self._settings = settings
        self._embeddings = HuggingFaceEmbeddings(
            model_name=settings.embedding_model,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        self._vectorstore = self._load_or_build_index()
        self._llm = ChatGroq(
            model=settings.llm_model,
            api_key=api_key,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
        self._chain = self._build_chain()

    @property
    def is_ready(self) -> bool:
        return self._vectorstore is not None

    # ─── Index management ──────────────────────────────────────────────
    def _load_or_build_index(self) -> FAISS | None:
        settings = self._settings
        index_file = settings.db_dir / "index.faiss"

        if index_file.is_file():
            logger.info("Loading existing FAISS index from %s", settings.db_dir)
            return FAISS.load_local(
                str(settings.db_dir), self._embeddings, allow_dangerous_deserialization=True
            )

        if not any(Path(settings.docs_dir).glob("*.pdf")):
            logger.warning("No PDF files found in %s", settings.docs_dir)
            return None

        logger.info("Building FAISS index from PDFs in %s", settings.docs_dir)
        documents = PyPDFDirectoryLoader(str(settings.docs_dir)).load()
        if not documents:
            logger.warning("PDF loader returned no documents.")
            return None

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap
        )
        chunks = splitter.split_documents(documents)

        vectorstore = FAISS.from_documents(documents=chunks, embedding=self._embeddings)
        vectorstore.save_local(str(settings.db_dir))
        logger.info("FAISS index built and saved (%d chunks).", len(chunks))
        return vectorstore

    # ─── Chain construction ────────────────────────────────────────────
    def _build_chain(self):
        prompt = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), ("human", "{input}")])
        return prompt | self._llm | StrOutputParser()

    @staticmethod
    def _format_docs(docs: list) -> str:
        return "\n\n".join(d.page_content for d in docs) if docs else "EMPTY"

    # ─── Public API ─────────────────────────────────────────────────────
    def answer(self, query: str, history: str = "(no previous turns)") -> RagResult:
        if not self.is_ready:
            raise RuntimeError("RagEngine.answer() called while engine is not ready.")

        results = self._vectorstore.similarity_search_with_score(
            query, k=self._settings.retrieval_k
        )
        if not results:
            return RagResult(text="", top_score=None, status="out_of_scope")

        top_score = results[0][1]
        logger.info("Top similarity score: %.4f", top_score)

        if top_score > self._settings.similarity_threshold:
            return RagResult(text="", top_score=top_score, status="out_of_scope")

        docs = [doc for doc, _score in results]
        context = self._format_docs(docs)

        raw = self._invoke_with_retry(query=query, context=context, history=history).strip()

        if "NOT_FOUND" in raw or len(raw) < 4:
            return RagResult(text="", top_score=top_score, status="no_answer")

        return RagResult(text=raw, top_score=top_score, status="ok")

    # ─── Resilience ─────────────────────────────────────────────────────
    def _invoke_with_retry(self, query: str, context: str, history: str) -> str:
        """Retries transient Groq/network failures with exponential backoff."""
        settings = self._settings
        last_error: Exception | None = None

        for attempt in range(settings.llm_retry_attempts + 1):
            try:
                return self._chain.invoke({"input": query, "context": context, "history": history})
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "LLM call failed (attempt %d/%d): %s",
                    attempt + 1, settings.llm_retry_attempts + 1, exc,
                )
                if attempt < settings.llm_retry_attempts:
                    time.sleep(settings.llm_retry_base_delay_seconds * (2 ** attempt))

        assert last_error is not None
        raise last_error
