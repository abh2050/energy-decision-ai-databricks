from edip.core.preflight_stats import CallOutcome, PreflightCall, summarize


def _calls(valid: int, other: CallOutcome = CallOutcome.INVALID_JSON, total: int = 20):
    return [
        PreflightCall(
            index=i,
            outcome=CallOutcome.VALID if i < valid else other,
            latency_s=float(i + 1),
            prompt_tokens=100,
            completion_tokens=50,
        )
        for i in range(total)
    ]


def _summary(calls):
    return summarize(calls, endpoint="ep", prompt_version="v1", config_hash="abc")


def test_nineteen_of_twenty_passes():
    s = _summary(_calls(19))
    assert s.passed
    assert s.valid_calls == 19
    assert s.valid_rate == 0.95
    assert s.prompt_tokens == 2000
    assert s.completion_tokens == 1000


def test_eighteen_of_twenty_fails():
    assert not _summary(_calls(18)).passed


def test_fewer_than_twenty_calls_fails_even_if_all_valid():
    assert not _summary(_calls(19, total=19)).passed


def test_median_latency_excludes_timeouts():
    s = _summary(_calls(10, other=CallOutcome.TIMEOUT))
    # completed calls have latencies 1..10
    assert s.median_latency_s == 5.5
    assert s.outcomes[CallOutcome.TIMEOUT] == 10


def test_empty_calls():
    s = _summary([])
    assert not s.passed
    assert s.median_latency_s is None
    assert s.valid_rate == 0.0
