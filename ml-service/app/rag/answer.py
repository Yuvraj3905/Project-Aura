"""Grounded answer generation with an anti-hallucination guardrail.

If retrieval is weak (top score below threshold), we return a "don't know" answer
WITHOUT calling the LLM — the model never gets a chance to invent facts. When grounded,
the system prompt further constrains it to answer only from the supplied context.
"""
from ..config import settings
from ..llm import generate
from .retrieve import retrieve

SYSTEM_PROMPT = (
    "You are Aura, a precise B2B sales engineer assistant. Answer the question using "
    "ONLY the provided context. If the context does not contain the answer, say you do "
    "not have that information in the knowledge base. Never invent facts, version "
    "numbers, or limits. Be concise."
)

NO_ANSWER = "I don't have that information in the current knowledge base."


def is_grounded(chunks: list[dict], min_score: float) -> bool:
    """True if the best retrieved chunk clears the similarity threshold."""
    return bool(chunks) and chunks[0]["score"] >= min_score


def format_context(chunks: list[dict]) -> str:
    return "\n\n".join(
        f"[document {c['document_id']} · chunk {c['ordinal']}]\n{c['content']}"
        for c in chunks
    )


def answer_query(query: str, top_k: int | None = None) -> dict:
    chunks = retrieve(query, top_k)

    if not is_grounded(chunks, settings.retrieval_min_score):
        return {"answer": NO_ANSWER, "grounded": False, "citations": []}

    prompt = (
        f"Context:\n{format_context(chunks)}\n\n"
        f"Question: {query}\n\n"
        "Answer using only the context above."
    )
    answer = generate(prompt, system=SYSTEM_PROMPT)

    citations = [
        {"document_id": c["document_id"], "ordinal": c["ordinal"], "score": round(c["score"], 3)}
        for c in chunks
    ]
    return {"answer": answer, "grounded": True, "citations": citations}
