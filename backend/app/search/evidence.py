"""Deterministic, source-preserving selection of useful retrieved evidence."""

import re
from dataclasses import dataclass

from app.core.config import Settings
from app.search.schemas import EvidenceItem, SearchResult

WORD = re.compile(r"[a-z0-9]+", re.IGNORECASE)
SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
QUESTION_START = re.compile(
    r"^(?:(?:question|q)\s*[:.)-]\s*)?(?:how|what|when|where|which|who|why|"
    r"can|could|would|will|do|does|did|is|are|was|were|has|have|had)\b",
    re.IGNORECASE,
)
REFERENCE_MARKER = re.compile(
    r"\b(?:quick\s+reference|table\s+of\s+contents|question\s+bank|"
    r"test\s+questions?|sample\s+questions?|glossary|navigation|index)\b",
    re.IGNORECASE,
)
QUANTITY_QUESTION = re.compile(
    r"\bhow\s+(?:many|much|long)\b|\b(?:number|amount|duration)\s+of\b",
    re.IGNORECASE,
)
WHEN_QUESTION = re.compile(
    r"\b(?:when|how\s+soon|how\s+quickly|by\s+when|timeframe|deadline)\b",
    re.IGNORECASE,
)
FREQUENCY_QUESTION = re.compile(r"\bhow\s+(?:often|frequently)\b", re.IGNORECASE)
WHO_QUESTION = re.compile(r"\bwho\b", re.IGNORECASE)
NUMBER = (
    r"(?:\d+(?:\.\d+)?|zero|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|"
    r"nineteen|twenty|thirty|forty|fifty|sixty|ninety|hundred|a|an)"
)
QUANTITY_EVIDENCE = re.compile(
    rf"\b{NUMBER}(?:\s+[a-z]+){{0,3}}\s+"
    r"(?:days?|hours?|weeks?|months?|years?|minutes?|percent|per\s+cent)\b",
    re.IGNORECASE,
)
TIME_EVIDENCE = re.compile(
    rf"\b(?:within|before|after|by)\s+"
    rf"(?:{NUMBER}\s+)?(?:minutes?|hours?|days?|weeks?|months?|years?|the\s+"
    r"(?:same|next)\s+business\s+day)\b|"
    r"\bno\s+later\s+than\s+(?:the\s+)?[\w'-]+(?:\s+[\w'-]+){0,5}\s+"
    r"(?:time|date|deadline)\b|"
    r"\b(?:immediately|promptly|without\s+delay|as\s+soon\s+as\s+possible)\b",
    re.IGNORECASE,
)
FREQUENCY_EVIDENCE = re.compile(
    r"\b(?:daily|weekly|monthly|quarterly|annually|yearly|biweekly|fortnightly|"
    r"once|twice|every\s+(?:day|week|month|quarter|year|\d+\s+"
    r"(?:days?|weeks?|months?|quarters?|years?))|at\s+least\s+"
    r"(?:daily|weekly|monthly|quarterly|annually|yearly))\b",
    re.IGNORECASE,
)
ROLE_EVIDENCE = re.compile(
    r"\b(?:responsible|owner|owned\s+by|team|department|manager|administrator|"
    r"security\s+office|operations)\b",
    re.IGNORECASE,
)
DECLARATIVE_CUE = re.compile(
    r"\b(?:is|are|was|were|has|have|had|may|must|should|shall|will|can|"
    r"receive|provide|require|report|request|apply|carry|include|allow|"
    r"work|submit|take|remain|occur|notify|follow|complete|become)\w*\b",
    re.IGNORECASE,
)
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "by", "can", "could",
    "do", "does", "did", "for", "from", "get", "give", "has", "have", "had", "how",
    "i", "in", "into", "is", "it", "many", "may", "much", "must", "of", "on", "or",
    "our", "per", "please", "should", "staff", "tell", "the", "their", "them", "they",
    "to", "us", "we", "what", "when", "where", "which", "who", "why", "will", "with",
    "work", "working", "would", "people", "person", "receive",
    "days", "day", "hours", "hour", "weeks", "week", "months", "month", "years", "year",
    "time", "amount", "number", "long",
}
GENERIC_INTENT_TERMS = {
    "amount", "entitlement", "policy", "requirement", "rule", "standard", "period",
    "timeframe",
    "limit", "process", "procedure", "information", "detail", "option",
}
def normalize_source_whitespace(text: str) -> str:
    """Collapse layout whitespace without changing or rewriting source words."""
    return " ".join(text.split())


def _normalize_token(word: str) -> str:
    token = word.lower()
    if len(token) > 5 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 5 and token.endswith("ing"):
        token = token[:-3]
        if len(token) > 2 and token[-1] == token[-2]:
            token = token[:-1]
        return token
    if len(token) > 5 and token.endswith("ied"):
        return token[:-3] + "y"
    if len(token) > 5 and token.endswith("ed"):
        return token[:-2]
    if len(token) > 4 and token.endswith("ly"):
        return token[:-2]
    if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _tokens(text: str) -> list[str]:
    return [_normalize_token(word) for word in WORD.findall(text)]


def _question_terms(question: str) -> set[str]:
    return {term for term in _tokens(question) if term not in STOP_WORDS}


def _distinguishing_terms(question: str) -> set[str]:
    """Return query concepts that distinguish the requested subject from neighbors.

    Generic intent words can help describe what is being asked, but should not
    make a passage about a different policy/domain appear answerable.
    """
    return _question_terms(question) - GENERIC_INTENT_TERMS


def _is_question_like(text: str) -> bool:
    stripped = text.strip()
    return "?" in stripped or bool(QUESTION_START.match(stripped))


def _has_quantity(text: str) -> bool:
    return bool(QUANTITY_EVIDENCE.search(text))


def _answer_type_match(question: str, text: str) -> bool:
    if FREQUENCY_QUESTION.search(question) and FREQUENCY_EVIDENCE.search(text):
        return True
    if QUANTITY_QUESTION.search(question) and _has_quantity(text):
        return True
    if WHEN_QUESTION.search(question) and TIME_EVIDENCE.search(text):
        return True
    if WHO_QUESTION.search(question) and ROLE_EVIDENCE.search(text):
        return True
    return False


def _is_substantive_declarative(text: str) -> bool:
    if _is_question_like(text) or REFERENCE_MARKER.search(text):
        return False
    tokens = _tokens(text)
    if len(tokens) < 5:
        return False
    return (
        bool(QUANTITY_EVIDENCE.search(text))
        or bool(TIME_EVIDENCE.search(text))
        or bool(DECLARATIVE_CUE.search(text))
        or text.rstrip().endswith((".", "!", ";"))
    )


def _sentence_score(sentence: str, question: str, terms: set[str]) -> float:
    sentence_terms = set(_tokens(sentence))
    overlap = len(terms & sentence_terms)
    score = overlap * 2.0
    if _answer_type_match(question, sentence):
        score += 3.0
    if _is_substantive_declarative(sentence):
        score += 1.5
    if _is_question_like(sentence):
        score -= 5.0
    if REFERENCE_MARKER.search(sentence):
        score -= 3.0
    return score


def extract_passage(text: str, question: str) -> str:
    """Choose relevant declarative source sentences and preserve short context."""
    source = normalize_source_whitespace(text)
    sentences = [part.strip() for part in SENTENCE.split(source) if part.strip()]
    if not sentences:
        return source

    terms = _question_terms(question)
    if len(sentences) == 1:
        return source

    scored = [
        (_sentence_score(sentence, question, terms), index)
        for index, sentence in enumerate(sentences)
    ]
    viable = [
        (score, index)
        for score, index in scored
        if (terms & set(_tokens(sentences[index])))
        or _answer_type_match(question, sentences[index])
    ]
    if not viable:
        return source
    best_score, best_index = max(viable, key=lambda entry: (entry[0], -entry[1]))
    if best_score <= 0:
        return source

    chosen = {best_index}
    for adjacent in (best_index - 1, best_index + 1):
        if not 0 <= adjacent < len(sentences):
            continue
        sentence = sentences[adjacent]
        if _is_question_like(sentence) or REFERENCE_MARKER.search(sentence):
            continue
        adjacent_terms = set(_tokens(sentence))
        is_short_context = len(sentence) < 100 and sentence.rstrip().endswith((".", "!"))
        if terms & adjacent_terms or is_short_context:
            chosen.add(adjacent)
    return " ".join(sentences[index] for index in sorted(chosen))


def _token_set(text: str) -> set[str]:
    return set(_tokens(text))


def substantially_overlaps(left: str, right: str, threshold: float) -> bool:
    left_tokens, right_tokens = _token_set(left), _token_set(right)
    if not left_tokens or not right_tokens:
        return False
    if left_tokens <= right_tokens or right_tokens <= left_tokens:
        return True
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens) >= threshold


@dataclass(frozen=True)
class EvidenceAssessment:
    substantive: bool
    strong: bool
    score: float
    query_overlap: int
    concept_coverage: float
    vector_similarity: float | None


def _assess(
    result: SearchResult, passage: str, question: str, settings: Settings
) -> EvidenceAssessment:
    terms = _question_terms(question)
    concepts = _distinguishing_terms(question)
    passage_terms = set(_tokens(passage))
    overlap = len(terms & passage_terms)
    coverage = overlap / max(1, len(terms))
    concept_overlap = len(concepts & passage_terms)
    concept_coverage = concept_overlap / max(1, len(concepts))
    substantive = _is_substantive_declarative(passage)
    answer_match = _answer_type_match(question, passage)
    reference_material = bool(REFERENCE_MARKER.search(result.text))
    semantic_signal = (
        result.vector_similarity is not None
        and result.vector_similarity >= settings.evidence_minimum_vector_similarity
    )
    lexical_signal = (
        result.keyword_rank is not None
        and (result.keyword_score is None or result.keyword_score > 0)
        and overlap >= settings.evidence_minimum_query_term_overlap
        and concept_coverage >= settings.evidence_minimum_query_coverage
        and (
            not (
                QUANTITY_QUESTION.search(question)
                or FREQUENCY_QUESTION.search(question)
                or WHEN_QUESTION.search(question)
                or WHO_QUESTION.search(question)
            )
            or answer_match
        )
    )
    # Absolute vector similarity can bridge paraphrases, but only when the
    # passage also contains evidence of the answer type requested (frequency,
    # quantity, timing, or responsible role). Ordinary lexical support uses
    # FTS plus overlapping query concepts. Vector rank/RRF rank alone never
    # counts as semantic strength.
    strong = (
        substantive
        and not reference_material
        and (lexical_signal or semantic_signal and answer_match)
    )
    question_penalty = 5.0 if _is_question_like(passage) else 0.0
    reference_penalty = 3.0 if reference_material else 0.0
    score = (
        coverage * 4.0
        + concept_coverage * 3.0
        + min(overlap, 4) * 0.25
        + (2.0 if answer_match else 0.0)
        + (1.0 if substantive else -2.0)
        - question_penalty
        - reference_penalty
    )
    return EvidenceAssessment(
        substantive,
        strong,
        score,
        overlap,
        concept_coverage,
        result.vector_similarity,
    )


@dataclass(frozen=True)
class SelectedEvidence:
    best: EvidenceItem | None
    supporting: list[EvidenceItem]
    related: list[EvidenceItem]
    state: str


def _normalized_text(text: str) -> str:
    return " ".join(_tokens(text))


def _duplicate(
    result: SearchResult,
    item: EvidenceItem,
    previous: list[tuple[SearchResult, EvidenceItem]],
    threshold: float,
) -> bool:
    normalized = _normalized_text(item.text)
    for previous_result, previous_item in previous:
        if normalized == _normalized_text(previous_item.text):
            return True
        if substantially_overlaps(item.text, previous_item.text, threshold):
            return True
        same_source_page = (
            result.document_id == previous_result.document_id
            and result.page_start == previous_result.page_start
            and result.page_end == previous_result.page_end
        )
        if same_source_page and substantially_overlaps(
            result.text, previous_result.text, threshold
        ):
            return True
    return False


def _adds_context(candidate: EvidenceItem, selected: list[EvidenceItem]) -> bool:
    candidate_tokens = _token_set(candidate.text)
    existing_tokens = set().union(*(_token_set(item.text) for item in selected))
    novel = candidate_tokens - existing_tokens
    return len(novel) >= 2 or len(candidate_tokens) <= 4 and len(novel) >= 1


def select_evidence(
    results: list[SearchResult],
    *,
    question: str,
    workspace_id: str,
    settings: Settings,
) -> SelectedEvidence:
    """Assess evidence quality separately, then use retrieval rank as a tie-breaker."""
    candidates: list[tuple[SearchResult, EvidenceItem, EvidenceAssessment]] = []
    for result in results:
        passage = extract_passage(result.text, question)
        item = EvidenceItem(
            chunk_id=result.chunk_id,
            document_id=result.document_id,
            document_title=result.document_filename,
            text=passage,
            page_start=result.page_start,
            page_end=result.page_end,
            source_path=(
                f"/workspaces/{workspace_id}/documents/{result.document_id}"
                f"?page={result.page_start}"
            ),
            retrieval_rank=result.rank,
        )
        assessment = _assess(result, passage, question, settings)
        candidates.append((result, item, assessment))

    # Prefer content quality before retrieval's relevance ordering. Original rank
    # remains a deterministic tie-breaker rather than the evidence decision.
    candidates.sort(
        key=lambda entry: (
            -entry[2].score,
            -(entry[2].vector_similarity if entry[2].vector_similarity is not None else -1.0),
            entry[0].rank,
            str(entry[1].chunk_id),
        )
    )
    deduplicated: list[tuple[SearchResult, EvidenceItem, EvidenceAssessment]] = []
    for result, item, assessment in candidates:
        if not _duplicate(
            result,
            item,
            [
                (existing_result, existing_item)
                for existing_result, existing_item, _ in deduplicated
            ],
            settings.evidence_dedup_jaccard_threshold,
        ):
            deduplicated.append((result, item, assessment))

    strong = [entry for entry in deduplicated if entry[2].strong]
    if strong:
        best = strong[0][1]
        selected = [best]
        supporting: list[EvidenceItem] = []
        for _result, item, _assessment in strong[1:]:
            if len(supporting) >= settings.evidence_supporting_limit:
                break
            if not _adds_context(item, selected):
                continue
            supporting.append(item)
            selected.append(item)
        return SelectedEvidence(best, supporting, [], "evidence_found")

    weak = [
        item
        for _result, item, assessment in deduplicated
        if assessment.substantive and assessment.query_overlap > 0
    ][: settings.evidence_supporting_limit]
    if weak:
        return SelectedEvidence(None, [], weak, "weak_evidence")
    return SelectedEvidence(None, [], [], "no_evidence")
