import datetime

from oil import oil
import psycopg2.errors
import pytest

from fichub_net import limiter
from fichub_net.limiter import Limiter


class TestLimiter:
    def test_init(self) -> None:
        _lim = Limiter(
            1,
            "foo",
            10.0,
            1.0 / 1.0,
            0.0,
            datetime.datetime.now(tz=datetime.UTC),
        )

    @staticmethod
    def test_select_none() -> None:
        lim0 = Limiter.select("test-foo-0")
        assert lim0 is None

    @staticmethod
    def test_create() -> None:
        lim0 = Limiter.create("test-foo-0")
        assert lim0.key == "test-foo-0"
        assert lim0.capacity == limiter.DEFAULT_LIMITER_CAPACITY
        assert lim0.flow == limiter.DEFAULT_LIMITER_FLOW

        lim1 = Limiter.create("test-foo-1")
        assert lim1.key == "test-foo-1"

        with pytest.raises(
            psycopg2.errors.UniqueViolation, match=r".key.=.test-foo-1. already exists"
        ):
            Limiter.create("test-foo-1")

        Limiter.create("anon:test-foo-2")

    @staticmethod
    def test_select() -> None:
        lim0 = Limiter.select("test-foo-0")
        assert lim0 is not None

    def test_burst(self) -> None:
        lim0 = Limiter.select("test-foo-0")
        assert lim0 is not None
        burst = lim0.burst()
        assert burst > 0
        assert burst == lim0.capacity

    @pytest.mark.parametrize(
        ("key", "is_anon"),
        [("test-foo-0", False), ("test-foo-1", False), ("anon:test-foo-2", True)],
    )
    def test_is_anon(self, key: str, is_anon: bool) -> None:
        lim = Limiter.select(key)
        assert lim is not None
        assert lim.is_anon() is is_anon

    def test_set_parameters(self) -> None:
        lim1 = Limiter.select("test-foo-1")
        assert lim1 is not None
        burst = lim1.burst()
        assert burst > 0
        assert burst == limiter.DEFAULT_LIMITER_CAPACITY

        new_capacity = 5
        new_lim1 = lim1.set_parameters(new_capacity, 1.0 / 1.0)
        assert lim1.burst() == burst
        assert new_lim1.burst() == new_capacity

    def test_refresh(self) -> None:
        lim1 = Limiter.select("test-foo-1")
        assert lim1 is not None
        capacity = lim1.capacity

        new_capacity = 6
        with oil.open() as db, db.cursor() as curs:
            curs.execute(
                "update fichub.limiter set capacity = %s where id = %s",
                (new_capacity, lim1.id),
            )

        assert lim1.capacity == capacity

        new_lim1 = lim1.refresh()
        assert lim1.capacity == capacity
        assert new_lim1.capacity == new_capacity

    def test_retry_after(self) -> None:
        lim1 = Limiter.select("test-foo-1")
        assert lim1 is not None
        burst = lim1.burst()
        for _i in range(int(burst)):
            assert lim1.retry_after(1.0) is None

        res = lim1.retry_after(1.0)
        assert res is not None
        assert res > 0.5  # noqa: PLR2004
        assert res < 2.0  # noqa: PLR2004

        new_flow_s = 120.0
        lim1.set_parameters(lim1.capacity, 1.0 / new_flow_s)
        res = lim1.retry_after(1.0)
        assert res is not None
        assert res > (new_flow_s - 1.0)
        assert res < (new_flow_s + 1.0)

        # Missing limiters always return 60s
        with oil.open() as db, db.cursor() as curs:
            curs.execute(
                "delete from fichub.limiter where id = %s",
                (lim1.id,),
            )

        assert Limiter.select(lim1.key) is None

        missing_limiter_s = 60.0
        assert lim1.retry_after(1.0) == missing_limiter_s
        assert lim1.retry_after(0.0) == missing_limiter_s

    def test_tick(self) -> None:
        lim0 = Limiter.select("test-foo-0")
        assert lim0 is not None
        burst = lim0.burst()
        for i in range(int(burst)):
            assert lim0.tick(1.0) > i

        # Missing limiters return MissingLimiterError
        with oil.open() as db, db.cursor() as curs:
            curs.execute(
                "delete from fichub.limiter where id = %s",
                (lim0.id,),
            )

        assert Limiter.select(lim0.key) is None

        with pytest.raises(limiter.MissingLimiterError, match="no tick response"):
            lim0.tick(1.0)
