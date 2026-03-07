from typing import Any, Optional
import datetime

from oil import oil

DEFAULT_LIMITER_CAPACITY = 30
DEFAULT_LIMITER_FLOW = 1.0 / 8.6


class FillLimiterError(Exception):
    pass


class MissingLimiterError(Exception):
    pass


class Limiter:
    def __init__(
        self,
        id_: int,
        key_: str,
        capacity_: float,
        flow_: float,
        value_: float,
        last_drain_: datetime.datetime,
    ) -> None:
        self.id = id_
        self.key = key_
        self.capacity = capacity_
        self.flow = flow_
        self.value = value_
        self.last_drain = last_drain_

    def burst(self) -> float:
        return max(0, self.capacity - self.value)

    def is_anon(self) -> bool:
        return self.key.startswith("anon:")

    @staticmethod
    def from_row(row: Any) -> "Limiter":
        return Limiter(*row)

    @staticmethod
    def select(key: str) -> Optional["Limiter"]:
        with oil.open() as db, db.cursor() as curs:
            curs.execute(
                """
                select id, key, capacity, flow, value, lastDrain
                from fichub.limiter wl
                where wl.key = %s
                """,
                (key,),
            )
            r = curs.fetchone()
            return None if r is None else Limiter.from_row(r)

    @staticmethod
    def create(key: str) -> "Limiter":
        with oil.open() as db, db.cursor() as curs:
            curs.execute(
                """
                insert into fichub.limiter(key, capacity, flow, value, lastDrain)
                values(%s, %s, %s, %s, now())
                """,
                (key, DEFAULT_LIMITER_CAPACITY, DEFAULT_LIMITER_FLOW, 0),
            )
        limiter = Limiter.select(key)
        assert limiter is not None
        return limiter

    def set_parameters(self, capacity: float, flow: float) -> "Limiter":
        with oil.open() as db, db.cursor() as curs:
            curs.execute(
                """
                update fichub.limiter set capacity = %s, flow = %s, dflt = %s
                where key = %s
                """,
                (capacity, flow, False, self.key),
            )
        return self.refresh()

    def refresh(self) -> "Limiter":
        limiter = Limiter.select(self.key)
        assert limiter is not None
        return limiter

    def retry_after(self, value: float) -> float | None:
        with oil.open() as db, db.cursor() as curs:
            curs.execute("select fichub.fill_limiter(%s, %s)", (self.key, value))
            r = curs.fetchone()
            if r is None:
                msg = "Limiter.retryAfter: no fill limit response"
                raise FillLimiterError(msg)
            v = float(r[0])
            if v <= 0:
                return None
            return v

    def tick(self, value: float) -> float:
        with oil.open() as db, db.cursor() as curs:
            curs.execute(
                "update fichub.limiter set value = value + %s where key = %s returning value",
                (value, self.key),
            )
            r = curs.fetchone()
            if r is None:
                msg = "Limiter.tick: no tick response"
                raise MissingLimiterError(msg)
            return float(r[0])
