from typing import List


class QueryRewriter:
    """Generates query variants to improve recall in hybrid retrieval."""

    async def rewrite(self, query: str, domain: str, n_variants: int = 3) -> List[str]:
        # Stub: returns original + simple transformations
        # Production: use LLM to generate semantically diverse variants
        variants = [query]
        words = query.split()
        if len(words) > 3:
            variants.append(" ".join(words[: len(words) // 2]))
            variants.append(" ".join(words[len(words) // 2 :]))
        return variants[:n_variants]
