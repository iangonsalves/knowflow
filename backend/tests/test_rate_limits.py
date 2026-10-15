from app.core.rate_limits import ProcessRateLimiter


def test_question_token_bucket_enforces_burst_and_refill_per_user() -> None:
    limiter = ProcessRateLimiter()

    assert limiter.consume_question("owner-a", per_minute=60, burst=2, now=100) is None
    assert limiter.consume_question("owner-a", per_minute=60, burst=2, now=100) is None
    assert limiter.consume_question("owner-a", per_minute=60, burst=2, now=100) == 1
    assert limiter.consume_question("owner-b", per_minute=60, burst=2, now=100) is None
    assert limiter.consume_question("owner-a", per_minute=60, burst=2, now=101) is None


def test_upload_window_enforces_count_and_byte_limits_then_expires() -> None:
    limiter = ProcessRateLimiter()

    assert limiter.consume_upload(
        "owner-a", 8, uploads_per_hour=2, bytes_per_hour=12, now=100
    ) is None
    assert limiter.consume_upload(
        "owner-a", 5, uploads_per_hour=2, bytes_per_hour=12, now=101
    ) == 3_599
    assert limiter.consume_upload(
        "owner-b", 8, uploads_per_hour=2, bytes_per_hour=12, now=101
    ) is None
    assert limiter.consume_upload(
        "owner-a", 4, uploads_per_hour=2, bytes_per_hour=12, now=102
    ) is None
    assert limiter.consume_upload(
        "owner-a", 1, uploads_per_hour=2, bytes_per_hour=12, now=103
    ) == 3_597
    assert limiter.consume_upload(
        "owner-a", 8, uploads_per_hour=2, bytes_per_hour=12, now=3_701
    ) is None
