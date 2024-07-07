from typing import Any, Optional
import datetime

from oil import oil

DEFAULT_LIMITER_CAPACITY = 30
DEFAULT_LIMITER_FLOW = 1.0 / 8.6


class Limiter:
    def __init__(
        self,
        id_: int,
        key_: str,
        capacity_: float,
        flow_: float,
        value_: float,
        lastDrain_: datetime.datetime,
    ) -> None:
        self.id = id_
        self.key = key_
        self.capacity = capacity_
        self.flow = flow_
        self.value = value_
        self.lastDrain = lastDrain_

    def burst(self) -> float:
        return max(0, self.capacity - self.value)

    def isAnon(self) -> bool:
        return self.key.startswith("anon:")

    @staticmethod
    def fromRow(row: Any) -> "Limiter":
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
            return None if r is None else Limiter.fromRow(r)

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

    def refresh(self) -> "Limiter":
        limiter = Limiter.select(self.key)
        assert limiter is not None
        return limiter

    def retryAfter(self, value: float) -> Optional[float]:
        with oil.open() as db, db.cursor() as curs:
            curs.execute("select fichub.fill_limiter(%s, %s)", (self.key, value))
            r = curs.fetchone()
            if r is None:
                raise Exception("Limiter.retryAfter: no fill limit response")
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
            return float(r[0])

    # def retryAfterResponse(self, db: 'psycopg2.connection', value: float
    # ) -> Optional[ResponseReturnValue]:
    # retryAfter = self.retryAfter(db, value)
    # if retryAfter is None:
    # return None

    # retryAfter = int(math.ceil(retryAfter))

    # res = make_response(
    # {'err':-429,'msg':'too many requests','retryAfter':retryAfter},
    # 429)
    # res.headers['Retry-After'] = retryAfter
    # return res
