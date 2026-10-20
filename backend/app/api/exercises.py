"""API routes for the exercise library (Milestone 1).

Implements spec section 14:
- GET  /api/exercises - list/search/filter exercises
- GET  /api/exercises/:slug - single exercise
- POST /api/exercises/:slug/alternatives - find alternatives
- GET  /api/exercise-substitution-overrides - list overrides
- PUT  /api/exercise-substitution-overrides/:source/:target - set override
- DELETE /api/exercise-substitution-overrides/:source/:target - remove override
- GET  /api/exercises/filters - get filter options
- GET  /api/bjj-failure-types - list BJJ failure classifications
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.domain.exercise_library import (
    AlternativesRequest,
    ExerciseLibraryService,
    get_filter_options,
)

exercises_router = APIRouter()


class AlternativesRequestBody(BaseModel):
    available_equipment: list[str] = Field(default_factory=list)
    excluded_exercises: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    max_results: int = Field(default=5, ge=1, le=20)
    allow_advanced: bool = False


class OverrideRequestBody(BaseModel):
    decision: Literal["prefer", "allow", "exclude"]
    reason: str | None = Field(default=None, max_length=500)


@exercises_router.get("/exercises")
async def list_exercises(
    request: Request,
    search: str | None = Query(default=None, max_length=100),
    pattern: str | None = Query(default=None, max_length=40),
    intent: str | None = Query(default=None, max_length=20),
    region: str | None = Query(default=None, max_length=20),
    equipment: str | None = Query(default=None, max_length=40),
    bjj_tag: str | None = Query(default=None, max_length=40),
    substitution_group: str | None = Query(default=None, max_length=40),
    category: str | None = Query(default=None, max_length=20),
    active_only: bool = Query(default=True),
) -> dict:
    """List and filter exercises from the library.
    
    Supports searching by name/alias, and filtering by movement pattern,
    training intent, primary region, equipment, BJJ tag, substitution group,
    and category.
    """
    service: ExerciseLibraryService = request.app.state.exercise_library_service
    exercises = service.list_exercises(
        search=search,
        pattern=pattern,
        intent=intent,
        region=region,
        equipment=equipment,
        bjj_tag=bjj_tag,
        substitution_group=substitution_group,
        category=category,
        active_only=active_only,
    )
    return {"exercises": exercises, "count": len(exercises)}


@exercises_router.get("/exercises/filters")
async def get_exercise_filters() -> dict:
    """Get all valid filter option values for the exercise library."""
    return get_filter_options()


@exercises_router.get("/exercises/{slug}")
async def get_exercise(request: Request, slug: str) -> dict:
    """Get a single exercise by slug."""
    service: ExerciseLibraryService = request.app.state.exercise_library_service
    exercise = service.get_exercise(slug)
    if exercise is None:
        raise HTTPException(status_code=404, detail="Exercise not found.")
    return exercise


@exercises_router.post("/exercises/{slug}/alternatives")
async def find_alternatives(
    request: Request,
    slug: str,
    body: AlternativesRequestBody,
) -> dict:
    """Find alternative exercises for a given source exercise.
    
    Uses the deterministic alternatives engine from spec section 8.
    """
    service: ExerciseLibraryService = request.app.state.exercise_library_service
    
    source = service.get_exercise(slug)
    if source is None:
        raise HTTPException(status_code=404, detail="Exercise not found.")

    alternatives_request = AlternativesRequest(
        source_exercise_slug=slug,
        available_equipment=frozenset(body.available_equipment),
        excluded_exercises=frozenset(body.excluded_exercises),
        limitations=frozenset(body.limitations),
        max_results=body.max_results,
        allow_advanced=body.allow_advanced,
    )

    result = service.find_alternatives(alternatives_request)

    return {
        "source": result.source,
        "alternatives": [
            {
                "slug": alt.slug,
                "name": alt.name,
                "score": alt.score,
                "why": list(alt.why),
                "tradeoff": alt.tradeoff,
            }
            for alt in result.alternatives
        ],
    }


@exercises_router.get("/exercise-substitution-overrides")
async def list_overrides(
    request: Request,
    source: str | None = Query(default=None, max_length=80),
) -> dict:
    """List user overrides for exercise substitutions."""
    service: ExerciseLibraryService = request.app.state.exercise_library_service
    overrides = service.get_overrides(source_slug=source)
    return {"overrides": overrides, "count": len(overrides)}


@exercises_router.put("/exercise-substitution-overrides/{source}/{target}")
async def set_override(
    request: Request,
    source: str,
    target: str,
    body: OverrideRequestBody,
) -> dict:
    """Set or update a user override for exercise substitution.
    
    - prefer: prefer this alternative over others
    - allow: explicitly allow this alternative (useful when combined with limitations)
    - exclude: never suggest this alternative
    """
    service: ExerciseLibraryService = request.app.state.exercise_library_service
    try:
        return service.set_override(
            source_slug=source,
            target_slug=target,
            decision=body.decision,
            reason=body.reason,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@exercises_router.delete("/exercise-substitution-overrides/{source}/{target}")
async def delete_override(
    request: Request,
    source: str,
    target: str,
) -> dict:
    """Delete a user override for exercise substitution."""
    service: ExerciseLibraryService = request.app.state.exercise_library_service
    deleted = service.delete_override(source_slug=source, target_slug=target)
    if not deleted:
        raise HTTPException(status_code=404, detail="Override not found.")
    return {"status": "deleted"}


@exercises_router.get("/bjj-failure-types")
async def list_bjj_failure_types(request: Request) -> dict:
    """List all BJJ failure type classifications."""
    service: ExerciseLibraryService = request.app.state.exercise_library_service
    failure_types = service.get_bjj_failure_types()
    return {"failure_types": failure_types, "count": len(failure_types)}
