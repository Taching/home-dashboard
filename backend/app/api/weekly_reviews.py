"""Weekly analyzer API routes (spec section 14). Additive to existing training week review."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Request

from app.core.settings import settings
from app.domain.weekly_coach import ask_coach

weekly_reviews_router = APIRouter()


@weekly_reviews_router.get("/weekly-reviews/latest")
async def latest_weekly_review(request: Request) -> dict:
    service = getattr(request.app.state, "weekly_analyzer_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Weekly analyzer not configured.")
    payload = service.latest()
    if payload is None:
        raise HTTPException(status_code=404, detail="No weekly analysis saved yet.")
    return payload


@weekly_reviews_router.get("/weekly-reviews/{week_start}")
async def get_weekly_review(request: Request, week_start: date) -> dict:
    service = getattr(request.app.state, "weekly_analyzer_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Weekly analyzer not configured.")
    payload = service.get(week_start)
    if payload is None:
        # Lazy recompute so opening /weekly always has a deterministic report.
        try:
            payload = service.recompute(week_start)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
    return payload


@weekly_reviews_router.post("/weekly-reviews/{week_start}/recompute")
async def recompute_weekly_review(request: Request, week_start: date) -> dict:
    service = getattr(request.app.state, "weekly_analyzer_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Weekly analyzer not configured.")
    try:
        return service.recompute(week_start)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@weekly_reviews_router.post("/weekly-reviews/{week_start}/ask-coach")
async def ask_coach_weekly_review(request: Request, week_start: date) -> dict:
    """Explicit Ask coach about this week. Never runs automatically."""
    service = getattr(request.app.state, "weekly_analyzer_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Weekly analyzer not configured.")
    analysis = service.get(week_start)
    if analysis is None:
        analysis = service.recompute(week_start)

    report, status = ask_coach(analysis, model_name=settings.voice_command_model)
    if report is None:
        return {
            "status": status,
            "message": "Coach unavailable. Deterministic report is still shown.",
            "analysis": analysis,
        }

    model_name = settings.voice_command_model or "gpt-4.1-mini"
    if status == "dry_run":
        model_name = f"dry-run:{model_name}"
    saved = service.save_coach_report(week_start, report, model_name=model_name)
    return {"status": status, "analysis": saved}
