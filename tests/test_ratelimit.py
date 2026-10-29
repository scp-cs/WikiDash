from wikidash.ratelimit import RateLimiter


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def test_burst_then_wait() -> None:
    t = FakeTime()
    limiter = RateLimiter(60, 45, clock=t.clock, sleep=t.sleep)  # 1 token / 0.75s
    for _ in range(60):
        limiter.acquire()
    assert t.slept == []
    limiter.acquire()
    assert abs(sum(t.slept) - 0.75) < 1e-9


def test_refill_is_capped() -> None:
    t = FakeTime()
    limiter = RateLimiter(2, 2, clock=t.clock, sleep=t.sleep)
    t.now = 1000
    for _ in range(2):
        limiter.acquire()
    assert t.slept == []
    limiter.acquire()
    assert t.slept
