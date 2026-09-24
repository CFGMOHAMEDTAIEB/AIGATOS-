from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import Base, get_db
from app.repositories.crud import get_one, list_all, remove, save


def crud_router(
    path: str,
    tag: str,
    model: type[Base],
    create_schema: type[BaseModel],
    update_schema: type[BaseModel],
    read_schema: type[BaseModel],
    references: dict[str, type[Base]] | None = None,
) -> APIRouter:
    router = APIRouter(prefix=path, tags=[tag])
    references = references or {}

    def check_references(db: Session, values: dict[str, Any]) -> None:
        for field, target in references.items():
            if field in values and get_one(db, target, values[field]) is None:
                raise HTTPException(status_code=404, detail=f"{field} not found")

    def commit_or_conflict(db: Session, action: Callable[[], Any]) -> Any:
        try:
            return action()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail="Resource conflict or resource in use") from exc

    @router.post("", response_model=read_schema, status_code=status.HTTP_201_CREATED)
    def create(payload: create_schema, db: Session = Depends(get_db)) -> Any:
        values = payload.model_dump()
        check_references(db, values)
        return commit_or_conflict(db, lambda: save(db, model(**values)))

    @router.get("", response_model=list[read_schema])
    def list_items(
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=100),
        db: Session = Depends(get_db),
    ) -> Any:
        return list_all(db, model, offset, limit)

    @router.get("/{object_id}", response_model=read_schema)
    def retrieve(object_id: str, db: Session = Depends(get_db)) -> Any:
        obj = get_one(db, model, object_id)
        if obj is None:
            raise HTTPException(status_code=404, detail="Resource not found")
        return obj

    @router.patch("/{object_id}", response_model=read_schema)
    def update(object_id: str, payload: update_schema, db: Session = Depends(get_db)) -> Any:
        obj = get_one(db, model, object_id)
        if obj is None:
            raise HTTPException(status_code=404, detail="Resource not found")
        values = payload.model_dump(exclude_unset=True)
        if any(value is None for value in values.values()):
            raise HTTPException(status_code=422, detail="Fields cannot be null")
        check_references(db, values)
        for field, value in values.items():
            setattr(obj, field, value)
        return commit_or_conflict(db, lambda: save(db, obj))

    @router.delete("/{object_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete(object_id: str, db: Session = Depends(get_db)) -> Response:
        obj = get_one(db, model, object_id)
        if obj is None:
            raise HTTPException(status_code=404, detail="Resource not found")
        commit_or_conflict(db, lambda: remove(db, obj))
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
