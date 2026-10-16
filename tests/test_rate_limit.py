from fastapi import HTTPException

from app.core.rate_limit import DAY, HOUR, RateLimiter


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def blocked(limiter: RateLimiter, ip: str) -> bool:
    try:
        limiter.check(ip)
        return False
    except HTTPException as e:
        assert e.status_code == 429
        return True


def test_per_ip_limit_and_reset_after_an_hour():
    clock = FakeClock()
    limiter = RateLimiter(per_ip_per_hour=2, global_per_day=100, clock=clock)
    assert [blocked(limiter, "1.1.1.1") for _ in range(3)] == [False, False, True]
    assert not blocked(limiter, "2.2.2.2")  # other visitors unaffected
    clock.now += HOUR
    assert not blocked(limiter, "1.1.1.1")


def test_global_daily_cap_applies_across_ips():
    clock = FakeClock()
    limiter = RateLimiter(per_ip_per_hour=100, global_per_day=3, clock=clock)
    assert [blocked(limiter, f"10.0.0.{i}") for i in range(4)] == [False, False, False, True]
    clock.now += DAY
    assert not blocked(limiter, "10.0.0.9")


def test_blocked_requests_do_not_count():
    clock = FakeClock()
    limiter = RateLimiter(per_ip_per_hour=1, global_per_day=2, clock=clock)
    assert not blocked(limiter, "1.1.1.1")
    assert blocked(limiter, "1.1.1.1")
    assert not blocked(limiter, "9.9.9.9")  # blocked call didn't use up the global cap
