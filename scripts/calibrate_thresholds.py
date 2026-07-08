"""
Calibrate FAISS L2 similarity thresholds for paraphrase-multilingual-MiniLM-L12-v2.

Usage:
    python scripts/calibrate_thresholds.py

Loads the company FAISS index from faiss_db/, runs 20 golden questions
(10 AR / 10 EN on-topic + 4 off-topic), and prints each question's top-3
L2 scores so you can set similarity_threshold and min_score_to_show_source
in config.py correctly.

Lower L2 score = more similar.
"""
from __future__ import annotations

import sys
import os

# Make sure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GOLDEN_QUESTIONS: list[tuple[str, str]] = [
    # ── On-topic English ──────────────────────────────────────────────────
    ("EN-on", "How many days of annual leave am I entitled to?"),
    ("EN-on", "What is the sick leave policy?"),
    ("EN-on", "How do I apply for travel reimbursement?"),
    ("EN-on", "What are the end of service gratuity rules?"),
    ("EN-on", "What are the official working hours?"),
    ("EN-on", "What is the dress code policy?"),
    ("EN-on", "How many days of maternity leave are allowed?"),
    ("EN-on", "What is the policy for emergency leave?"),
    ("EN-on", "How do I request a promotion?"),
    ("EN-on", "What are the overtime compensation rules?"),
    # ── On-topic Arabic ───────────────────────────────────────────────────
    ("AR-on", "كم عدد أيام الإجازة السنوية المستحقة؟"),
    ("AR-on", "ما هي سياسة الإجازة المرضية؟"),
    ("AR-on", "كيف أتقدم بطلب بدل السفر؟"),
    ("AR-on", "ما هي قواعد مكافأة نهاية الخدمة؟"),
    ("AR-on", "ما هي ساعات العمل الرسمية؟"),
    ("AR-on", "ما هو نظام اللباس في الشركة؟"),
    ("AR-on", "كم يوم إجازة أمومة مسموح بها؟"),
    ("AR-on", "ما سياسة الإجازة الطارئة؟"),
    ("AR-on", "كيف أطلب الترقية الوظيفية؟"),
    ("AR-on", "ما قواعد التعويض عن العمل الإضافي؟"),
    # ── Off-topic ─────────────────────────────────────────────────────────
    ("OFF",   "What is the capital of France?"),
    ("OFF",   "How do I make a chocolate cake?"),
    ("OFF",   "Explain quantum entanglement."),
    ("OFF",   "Who won the World Cup in 2022?"),
]

TOP_K = 3


def main() -> None:
    try:
        from langchain_community.vectorstores import FAISS
        from langchain_community.embeddings import FastEmbedEmbeddings
    except ImportError:
        print("ERROR: langchain_community not installed. Run: pip install langchain-community fastembed")
        sys.exit(1)

    index_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "faiss_db")
    if not os.path.exists(os.path.join(index_path, "index.faiss")):
        print(f"ERROR: FAISS index not found at {index_path}. Build it first.")
        sys.exit(1)

    print("Loading embedding model (first run may download weights)…")
    embeddings = FastEmbedEmbeddings(
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )

    print(f"Loading FAISS index from {index_path}…\n")
    db = FAISS.load_local(index_path, embeddings, allow_dangerous_deserialization=True)

    col_q   = 55
    col_s   = 10
    header  = f"{'Type':<7}  {'Question':<{col_q}}  {'Score-1':>{col_s}}  {'Score-2':>{col_s}}  {'Score-3':>{col_s}}"
    divider = "-" * len(header)

    print(header)
    print(divider)

    on_topic_scores:  list[float] = []
    off_topic_scores: list[float] = []

    for tag, question in GOLDEN_QUESTIONS:
        results = db.similarity_search_with_score(question, k=TOP_K)
        scores  = [round(s, 4) for _, s in results]
        # Pad if fewer than TOP_K results returned
        while len(scores) < TOP_K:
            scores.append(float("inf"))

        q_display = question if len(question) <= col_q else question[: col_q - 1] + "~"
        row = f"{tag:<7}  {q_display:<{col_q}}  {scores[0]:>{col_s}.4f}  {scores[1]:>{col_s}.4f}  {scores[2]:>{col_s}.4f}"
        print(row.encode("ascii", errors="replace").decode("ascii"))

        if tag.endswith("-on"):
            on_topic_scores.append(scores[0])
        else:
            off_topic_scores.append(scores[0])

    print(divider)
    print(f"\nOn-topic  best-score range : {min(on_topic_scores):.4f} – {max(on_topic_scores):.4f}")
    print(f"Off-topic best-score range : {min(off_topic_scores):.4f} – {max(off_topic_scores):.4f}")
    print()

    # Suggest a threshold that accepts all on-topic and rejects all off-topic
    safe_threshold = (max(on_topic_scores) + min(off_topic_scores)) / 2
    safe_source    = max(on_topic_scores) * 0.6   # show inline badge for clearly close hits
    print(f"Suggested similarity_threshold    : {safe_threshold:.2f}")
    print(f"Suggested min_score_to_show_source: {safe_source:.2f}")
    print()
    print("Update config.py with these values and add a comment with the measured ranges above.")


if __name__ == "__main__":
    main()
