from __future__ import annotations

from datetime import UTC, datetime
from secrets import token_urlsafe

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint


db = SQLAlchemy()


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class Session(TimestampMixin, db.Model):
    __tablename__ = "sessions"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    code = db.Column(db.String(6), nullable=False, unique=True, index=True)
    status = db.Column(db.String(20), nullable=False, default="draft")
    active_question_index = db.Column(db.Integer, nullable=False, default=0)
    config_json = db.Column(db.JSON, nullable=False, default=dict)

    questions = db.relationship(
        "Question",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Question.position",
    )
    participants = db.relationship(
        "Participant",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    responses = db.relationship(
        "Response",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    runs = db.relationship(
        "SessionRun",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="SessionRun.run_number",
    )

    @property
    def active_question(self) -> "Question | None":
        ordered = sorted(self.questions, key=lambda item: item.position)
        if not ordered:
            return None
        index = min(max(self.active_question_index, 0), len(ordered) - 1)
        return ordered[index]


class SessionRun(TimestampMixin, db.Model):
    __tablename__ = "session_runs"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False)
    run_number = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="active")
    started_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    ended_at = db.Column(db.DateTime)
    summary_json = db.Column(db.JSON, nullable=False, default=dict)

    session = db.relationship("Session", back_populates="runs")
    responses = db.relationship("Response", back_populates="run")

    __table_args__ = (
        UniqueConstraint("session_id", "run_number", name="uq_session_run_number"),
    )


class Question(TimestampMixin, db.Model):
    __tablename__ = "questions"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False)
    type = db.Column(db.String(30), nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    prompt = db.Column(db.Text, nullable=False)
    position = db.Column(db.Integer, nullable=False)
    is_open = db.Column(db.Boolean, nullable=False, default=True)
    config_json = db.Column(db.JSON, nullable=False, default=dict)

    session = db.relationship("Session", back_populates="questions")
    options = db.relationship(
        "Option",
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="Option.position",
    )
    responses = db.relationship(
        "Response",
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="Response.created_at",
    )

    __table_args__ = (
        UniqueConstraint("session_id", "position", name="uq_question_session_position"),
    )


class Option(TimestampMixin, db.Model):
    __tablename__ = "options"

    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    label = db.Column(db.String(180), nullable=False)
    position = db.Column(db.Integer, nullable=False)
    is_correct = db.Column(db.Boolean, nullable=False, default=False)

    question = db.relationship("Question", back_populates="options")

    __table_args__ = (
        UniqueConstraint("question_id", "position", name="uq_option_question_position"),
    )


class Participant(TimestampMixin, db.Model):
    __tablename__ = "participants"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False)
    token = db.Column(db.String(120), nullable=False, default=lambda: token_urlsafe(32))
    connected = db.Column(db.Boolean, nullable=False, default=False)
    score = db.Column(db.Integer, nullable=False, default=0)
    last_seen_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    session = db.relationship("Session", back_populates="participants")
    responses = db.relationship(
        "Response",
        back_populates="participant",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("session_id", "token", name="uq_participant_session_token"),
    )


class Response(TimestampMixin, db.Model):
    __tablename__ = "responses"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False)
    run_id = db.Column(db.Integer, db.ForeignKey("session_runs.id"), nullable=True, index=True)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    participant_id = db.Column(db.Integer, db.ForeignKey("participants.id"), nullable=False)
    response_key = db.Column(db.String(80), nullable=False, default="default")
    payload_json = db.Column(db.JSON, nullable=False, default=dict)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    score_awarded = db.Column(db.Integer, nullable=False, default=0)

    session = db.relationship("Session", back_populates="responses")
    run = db.relationship("SessionRun", back_populates="responses")
    question = db.relationship("Question", back_populates="responses")
    participant = db.relationship("Participant", back_populates="responses")

    __table_args__ = (
        UniqueConstraint("question_id", "participant_id", "response_key", "run_id", name="uq_response_question_participant_run_key"),
    )
