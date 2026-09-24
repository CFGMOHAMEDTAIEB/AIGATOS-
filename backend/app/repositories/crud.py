from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base

ModelT = TypeVar("ModelT", bound=Base)


def get_one(db: Session, model: type[ModelT], object_id: str) -> ModelT | None:
    return db.get(model, object_id)


def list_all(db: Session, model: type[ModelT], offset: int, limit: int) -> list[ModelT]:
    return list(db.scalars(select(model).order_by(model.created_at, model.id).offset(offset).limit(limit)))


def save(db: Session, obj: ModelT) -> ModelT:
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def remove(db: Session, obj: Base) -> None:
    db.delete(obj)
    db.commit()
