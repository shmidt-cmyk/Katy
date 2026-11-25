from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import DeclarativeBase, Mapped, relationship

MYSQL_LONGTEXT = Text().with_variant(LONGTEXT(), "mysql")


class Base(DeclarativeBase):
    pass


class Vacancy(Base):
    __tablename__ = "jobpipe_vacancies"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = Column(String(255), nullable=False)
    employer_name: Mapped[str] = Column(String(255), default="", nullable=False)
    city: Mapped[str | None] = Column(String(120))
    url: Mapped[str] = Column(String(512), nullable=False, unique=True)
    description: Mapped[str | None] = Column(MYSQL_LONGTEXT)
    salary: Mapped[str] = Column(String(255), default="", nullable=False)
    source: Mapped[str] = Column(String(32), default="manual", nullable=False)
    status: Mapped[str] = Column(String(40), default="new", nullable=False)
    created_at: Mapped[datetime] = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    letters: Mapped[list["GeneratedLetter"]] = relationship(back_populates="vacancy")
    events: Mapped[list["ApplicationEvent"]] = relationship(back_populates="vacancy")


class GeneratedLetter(Base):
    __tablename__ = "jobpipe_letters"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    vacancy_id: Mapped[int] = Column(Integer, ForeignKey("jobpipe_vacancies.id", ondelete="CASCADE"), nullable=False)
    letter_text: Mapped[str] = Column(MYSQL_LONGTEXT, nullable=False)
    model_name: Mapped[str] = Column(String(64), default="gemini-2.0-flash", nullable=False)
    created_at: Mapped[datetime] = Column(DateTime, server_default=func.now(), nullable=False)

    vacancy: Mapped[Vacancy] = relationship(back_populates="letters")


class ApplicationEvent(Base):
    __tablename__ = "jobpipe_application_events"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    vacancy_id: Mapped[int] = Column(Integer, ForeignKey("jobpipe_vacancies.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = Column(String(40), nullable=False)
    note: Mapped[str | None] = Column(Text)
    created_at: Mapped[datetime] = Column(DateTime, server_default=func.now(), nullable=False)

    vacancy: Mapped[Vacancy] = relationship(back_populates="events")
