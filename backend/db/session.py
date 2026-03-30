from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


class PostgresSessionFactory:
    def __init__(self, dsn: str) -> None:
        self._engine = create_engine(dsn, pool_pre_ping=True)
        self._session_maker = sessionmaker(bind=self._engine, autoflush=False, autocommit=False)

    @property
    def engine(self):
        return self._engine

    def session(self) -> Session:
        return self._session_maker()

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        session = self.session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
