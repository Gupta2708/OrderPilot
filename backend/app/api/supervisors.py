"""Supervisor configuration endpoints."""

import uuid

from fastapi import APIRouter, HTTPException, status

from app import repository
from app.api.deps import SessionDep
from app.api.schemas import SupervisorCreate, SupervisorResponse

router = APIRouter(prefix="/api/supervisors", tags=["supervisors"])


@router.post("", response_model=SupervisorResponse, status_code=status.HTTP_201_CREATED)
async def create_supervisor(payload: SupervisorCreate, session: SessionDep) -> SupervisorResponse:
    supervisor = await repository.create_supervisor(
        session,
        name=payload.name,
        base_instruction=payload.base_instruction,
        allowed_actions=payload.allowed_actions,
        config={
            "wake_aggressiveness": str(payload.wake_aggressiveness),
            "default_wake_minutes": payload.default_wake_minutes,
            "max_age_minutes": payload.max_age_minutes,
            "require_approval_for": payload.require_approval_for,
        },
    )
    return SupervisorResponse.model_validate(supervisor)


@router.get("", response_model=list[SupervisorResponse])
async def list_supervisors(session: SessionDep) -> list[SupervisorResponse]:
    supervisors = await repository.list_supervisors(session)
    return [SupervisorResponse.model_validate(item) for item in supervisors]


@router.get("/{supervisor_id}", response_model=SupervisorResponse)
async def get_supervisor(supervisor_id: uuid.UUID, session: SessionDep) -> SupervisorResponse:
    try:
        supervisor = await repository.get_supervisor(session, supervisor_id)
    except repository.NotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return SupervisorResponse.model_validate(supervisor)
