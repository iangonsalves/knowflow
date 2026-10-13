import json
from pathlib import Path
from uuid import uuid4

from app.core.config import Settings
from app.search.evidence import extract_passage, select_evidence
from app.search.schemas import SearchResult


def make_result(
    text: str,
    *,
    document_id=None,
    page_start: int = 2,
    page_end: int = 2,
    rank: int = 1,
    document_filename: str = "Policy.pdf",
    keyword_rank: int | None = 1,
    vector_rank: int | None = 1,
    keyword_score: float | None = 0.02,
    vector_similarity: float | None = 0.80,
) -> SearchResult:
    return SearchResult(
        chunk_id=uuid4(),
        document_id=document_id or uuid4(),
        document_filename=document_filename,
        chunk_index=rank - 1,
        text=text,
        page_start=page_start,
        page_end=page_end,
        rank=rank,
        rrf_score=0.02,
        keyword_rank=keyword_rank,
        vector_rank=vector_rank,
        keyword_score=keyword_score,
        vector_similarity=vector_similarity,
    )


def test_passage_extraction_is_deterministic_verbatim_and_keeps_context() -> None:
    source = (
        "The policy applies to full-time employees. "
        "Full-time employees receive 25 working days of paid annual leave each year. "
        "Requests should be submitted through the HR system."
    )
    first = extract_passage(source, "How much annual leave do employees receive?")
    second = extract_passage(source, "How much annual leave do employees receive?")

    assert first == second
    assert "receive 25 working days of paid annual leave" in first
    assert first.startswith("The policy applies")
    assert first.endswith("Requests should be submitted through the HR system.")
    assert first.replace(" ", "") in source.replace(" ", "")


def test_passage_extraction_falls_back_to_full_chunk_for_semantic_only_query() -> None:
    source = "Full-time employees receive 25 working days of paid annual leave."
    assert extract_passage(source, "How much vacation time do staff get?") == source


def test_evidence_selects_best_support_and_collapses_overlapping_same_page() -> None:
    document_id = uuid4()
    rows = [
        make_result(
            "Employees receive 25 working days of paid annual leave each year.",
            document_id=document_id,
            rank=1,
        ),
        make_result(
            "Employees receive 25 working days of paid annual leave each year. "
            "Requests go through HR.",
            document_id=document_id,
            rank=2,
            keyword_rank=2,
            vector_rank=2,
        ),
        make_result(
            "Annual leave requests should normally be made ten days ahead.",
            document_id=document_id,
            rank=3,
            keyword_rank=3,
            vector_rank=3,
        ),
    ]

    selected = select_evidence(
        rows,
        question="How much annual leave do employees receive?",
        workspace_id="workspace-1",
        settings=Settings(_env_file=None, app_env="test"),
    )

    assert selected.state == "evidence_found"
    assert selected.best is not None
    assert "25 working days" in selected.best.text
    assert len(selected.supporting) == 1
    assert selected.supporting[0].page_start == 2
    assert selected.best.source_path.endswith("?page=2")
    assert selected.best.document_id == document_id
    assert selected.best.text not in [item.text for item in selected.supporting]


def test_remote_policy_statement_beats_higher_ranked_test_question() -> None:
    document_id = uuid4()
    rows = [
        make_result(
            "Quick Reference for Testing. Question: How many remote-working days are allowed?",
            document_id=document_id,
            page_start=6,
            page_end=6,
            rank=1,
        ),
        make_result(
            "Eligible employees may work remotely for up to two days per week, "
            "subject to line-manager approval and business requirements.",
            document_id=document_id,
            page_start=3,
            page_end=3,
            rank=2,
        ),
    ]
    selected = select_evidence(
        rows,
        question="How many days can employees work remotely?",
        workspace_id="workspace-1",
        settings=Settings(_env_file=None, app_env="test"),
    )

    assert selected.state == "evidence_found"
    assert selected.best is not None
    assert "up to two days per week" in selected.best.text
    assert selected.best.page_start == 3
    assert selected.best.text not in [item.text for item in selected.supporting]
    assert all("Quick Reference" not in item.text for item in selected.supporting)


def test_semantic_vacation_query_prefers_substantive_quantity_passage() -> None:
    results = [
        make_result(
            "Question: How much vacation time do staff get?",
            rank=1,
        ),
        make_result(
            "Full-time employees receive 25 working days of paid annual leave per calendar year.",
            rank=3,
        ),
    ]
    selected = select_evidence(
        results,
        question="How much vacation time do staff get?",
        workspace_id="workspace-1",
        settings=Settings(_env_file=None, app_env="test"),
    )

    assert selected.best is not None
    assert "25 working days" in selected.best.text


def test_supporting_limit_zero_does_not_add_a_passage() -> None:
    settings = Settings(_env_file=None, app_env="test", evidence_supporting_limit=0)
    selected = select_evidence(
        [
            make_result("Full-time employees receive 25 working days of annual leave."),
            make_result("Employees may carry forward 5 unused annual leave days.", rank=2),
        ],
        question="How many annual leave days do employees receive?",
        workspace_id="workspace-1",
        settings=settings,
    )

    assert selected.best is not None
    assert selected.supporting == []


def test_security_question_selects_declarative_timed_requirement() -> None:
    result = make_result(
        "Suspected information-security incidents must be reported to IT Security "
        "within one hour of discovery.",
        page_start=4,
        page_end=4,
    )
    selected = select_evidence(
        [result],
        question="When must a security incident be reported?",
        workspace_id="workspace-1",
        settings=Settings(_env_file=None, app_env="test"),
    )

    assert selected.best is not None
    assert "within one hour" in selected.best.text
    assert selected.best.page_start == 4


def test_leaver_access_deadline_is_detected_as_time_evidence() -> None:
    selected = select_evidence(
        [
            make_result(
                "System access should be disabled no later than the employee's effective "
                "termination time. Higher-risk access may be removed earlier when authorized "
                "by HR and IT Security.",
                keyword_rank=None,
                keyword_score=None,
                vector_similarity=0.84,
            )
        ],
        question="When should a leaver's system access be removed?",
        workspace_id="workspace-1",
        settings=Settings(_env_file=None, app_env="test"),
    )

    assert selected.state == "evidence_found"
    assert selected.best is not None
    assert "effective termination time" in selected.best.text


def test_count_question_accepts_quantity_with_descriptive_words_before_unit() -> None:
    selected = select_evidence(
        [
            make_result(
                "Employees may carry forward up to 5 unused annual leave days into the next year."
            )
        ],
        question="How many unused leave days can carry into the next year?",
        workspace_id="workspace-1",
        settings=Settings(_env_file=None, app_env="test"),
    )

    assert selected.state == "evidence_found"
    assert selected.best is not None
    assert "5 unused annual leave days" in selected.best.text


def test_maternity_query_does_not_promote_unrelated_annual_leave() -> None:
    result = make_result(
        "Full-time employees receive 25 working days of paid annual leave each year."
    )
    selected = select_evidence(
        [result],
        question="What is the maternity leave entitlement?",
        workspace_id="workspace-1",
        settings=Settings(_env_file=None, app_env="test"),
    )

    assert selected.state == "weak_evidence"
    assert selected.best is None
    assert selected.supporting == []
    assert len(selected.related) == 1
    assert "annual leave" in selected.related[0].text


def test_semantic_signal_accepts_vacation_wording_without_a_domain_alias() -> None:
    selected = select_evidence(
        [
            make_result(
                "Full-time employees receive 25 working days of paid annual leave "
                "per calendar year.",
                rank=1,
                vector_rank=1,
                keyword_rank=None,
                keyword_score=None,
                vector_similarity=0.84,
            )
        ],
        question="How much vacation time do staff get?",
        workspace_id="workspace-1",
        settings=Settings(_env_file=None, app_env="test"),
    )

    assert selected.state == "evidence_found"
    assert selected.best is not None
    assert "25 working days" in selected.best.text


def test_vector_rank_one_alone_does_not_make_a_passage_strong() -> None:
    selected = select_evidence(
        [
            make_result(
                "Employees may work remotely for two days each week.",
                rank=1,
                keyword_rank=None,
                keyword_score=None,
                vector_rank=1,
                vector_similarity=0.48,
            )
        ],
        question="How many days can employees work remotely?",
        workspace_id="workspace-1",
        settings=Settings(_env_file=None, app_env="test"),
    )

    assert selected.state == "weak_evidence"
    assert selected.best is None


def test_semantic_frequency_evidence_supports_backup_schedule_paraphrase() -> None:
    selected = select_evidence(
        [
            make_result(
                "Technology Operations defines a backup schedule for each critical service "
                "with its owner. Critical business data is backed up at least daily.",
                keyword_rank=None,
                keyword_score=None,
                vector_rank=1,
                vector_similarity=0.82,
            )
        ],
        question="How often are backups performed?",
        workspace_id="workspace-1",
        settings=Settings(_env_file=None, app_env="test"),
    )

    assert selected.state == "evidence_found"
    assert selected.best is not None
    assert "backed up at least daily" in selected.best.text


def test_semantic_frequency_evidence_supports_privileged_access_review() -> None:
    selected = select_evidence(
        [
            make_result(
                "The owner of each critical service reviews privileged access at least quarterly.",
                keyword_rank=None,
                keyword_score=None,
                vector_rank=1,
                vector_similarity=0.82,
            )
        ],
        question="How often are administrator permissions reviewed?",
        workspace_id="workspace-1",
        settings=Settings(_env_file=None, app_env="test"),
    )

    assert selected.state == "evidence_found"
    assert selected.best is not None
    assert "privileged access at least quarterly" in selected.best.text


def test_multi_document_reporting_evidence_keeps_each_source_and_provenance() -> None:
    first_doc, second_doc = uuid4(), uuid4()
    selected = select_evidence(
        [
            make_result(
                "Anyone suspecting a security event must report it immediately.",
                document_id=first_doc,
                page_start=8,
                keyword_rank=None,
                keyword_score=None,
                vector_similarity=0.86,
            ),
            make_result(
                "Security incidents must be reported within one hour of discovery.",
                document_id=second_doc,
                page_start=4,
                rank=2,
                keyword_rank=None,
                keyword_score=None,
                vector_similarity=0.83,
            ),
        ],
        question="How quickly must a security incident be reported?",
        workspace_id="workspace-1",
        settings=Settings(_env_file=None, app_env="test"),
    )

    assert selected.state == "evidence_found"
    assert selected.best is not None
    assert selected.best.document_id in {first_doc, second_doc}
    assert selected.best.source_path.endswith(f"?page={selected.best.page_start}")
    assert selected.supporting
    assert selected.supporting[0].document_id != selected.best.document_id
    source_texts = [selected.best.text, *(item.text for item in selected.supporting)]
    assert any("immediately" in text for text in source_texts)
    assert any("within one hour" in text for text in source_texts)


def test_information_security_sample_generalization_cases() -> None:
    cases = json.loads(
        (Path(__file__).parent / "fixtures" / "security_evidence_eval.json").read_text()
    )
    settings = Settings(_env_file=None, app_env="test")

    for case in cases:
        selected = select_evidence(
            [
                make_result(
                    case["source_text"],
                    page_start=case["page"],
                    page_end=case["page"],
                    document_filename="KnowFlow_Sample_Information_Security_Policy.pdf",
                    keyword_rank=None,
                    keyword_score=None,
                    vector_rank=1,
                    vector_similarity=0.84,
                )
            ],
            question=case["query"],
            workspace_id="workspace-1",
            settings=settings,
        )

        assert selected.state == "evidence_found", case["query"]
        assert selected.best is not None, case["query"]
        assert case["expected_text"] in selected.best.text, case["query"]
        assert selected.best.document_title == "KnowFlow_Sample_Information_Security_Policy.pdf"
        assert selected.best.page_start == case["page"]


def test_security_sample_does_not_claim_unsupported_byod_allowance() -> None:
    selected = select_evidence(
        [
            make_result(
                "Employees may use personally owned devices only after they meet the "
                "company's security requirements.",
                keyword_rank=None,
                keyword_score=None,
                vector_rank=1,
                vector_similarity=0.79,
            )
        ],
        question="How much is the employee BYOD allowance?",
        workspace_id="workspace-1",
        settings=Settings(_env_file=None, app_env="test"),
    )

    assert selected.state in {"weak_evidence", "no_evidence"}
    assert selected.best is None
    assert selected.supporting == []


def test_distinguishing_query_concepts_block_related_but_wrong_subjects() -> None:
    cases = [
        (
            "What is the vendor termination period?",
            "The employee termination period is thirty days of notice.",
        ),
        (
            "What is the password reset timeframe?",
            "Passwords must meet complexity requirements and contain twelve characters.",
        ),
        (
            "What is the international transfer fee?",
            "Domestic transfers are processed without charge within one business day.",
        ),
    ]
    settings = Settings(_env_file=None, app_env="test")

    for question, unrelated_passage in cases:
        selected = select_evidence(
            [make_result(unrelated_passage, vector_rank=1)],
            question=question,
            workspace_id="workspace-1",
            settings=settings,
        )

        assert selected.state != "evidence_found", question
        assert selected.best is None, question
        assert selected.supporting == [], question


def test_identical_and_near_identical_passages_are_deduplicated_globally() -> None:
    document_id = uuid4()
    rows = [
        make_result(
            "Employees may work remotely for up to two days per week, subject to manager approval.",
            document_id=document_id,
            page_start=3,
            page_end=3,
            rank=1,
        ),
        make_result(
            "Employees may work remotely for up to two days per week subject to manager approval.",
            document_id=uuid4(),
            page_start=8,
            page_end=8,
            rank=2,
        ),
        make_result(
            "Remote workers may work two days per week and should secure manager approval "
            "before use.",
            document_id=uuid4(),
            page_start=5,
            page_end=5,
            rank=3,
        ),
    ]
    selected = select_evidence(
        rows,
        question="How many days can employees work remotely?",
        workspace_id="workspace-1",
        settings=Settings(_env_file=None, app_env="test"),
    )
    all_selected = ([selected.best] if selected.best else []) + selected.supporting

    assert selected.best is not None
    assert selected.best.text not in [item.text for item in selected.supporting]
    assert len(all_selected) == 2
    assert "secure manager approval" in selected.supporting[0].text


def test_question_only_candidates_are_no_evidence() -> None:
    selected = select_evidence(
        [
            make_result(
                "Question: What is the annual leave entitlement?",
                rank=1,
            )
        ],
        question="What is the annual leave entitlement?",
        workspace_id="workspace-1",
        settings=Settings(_env_file=None, app_env="test"),
    )

    assert selected.state == "no_evidence"
    assert selected.best is None
    assert selected.supporting == []
    assert selected.related == []


def test_retrieval_disagreement_is_weak_and_empty_results_are_no_evidence() -> None:
    settings = Settings(_env_file=None, app_env="test")
    weak = select_evidence(
        [make_result("Remote work can be requested by employees.", keyword_rank=None)],
        question="How many days can employees work remotely?",
        workspace_id="workspace-1",
        settings=settings,
    )
    none = select_evidence(
        [], question="Is our office on Mars?", workspace_id="workspace-1", settings=settings
    )

    assert weak.state == "weak_evidence"
    assert weak.best is None
    assert weak.supporting == []
    assert weak.related
    assert none.state == "no_evidence"
    assert none.best is None and none.supporting == [] and none.related == []
