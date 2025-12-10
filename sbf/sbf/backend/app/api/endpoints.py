"""
API endpoints for report generation.
Includes streaming endpoint with NDJSON responses.
"""

import asyncio
import json
from datetime import datetime
from typing import List
from fastapi import APIRouter, UploadFile, File, Form, Request, HTTPException
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
import structlog

from ..models.schemas import ProgressUpdate, ResultResponse, ErrorResponse, ReportType
from ..services.rag_service import RAGService
from ..core.config import settings

logger = structlog.get_logger()
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

# Lock for workflow initialization to prevent race conditions
_workflow_lock = asyncio.Lock()


@router.post("/generate-report")
@limiter.limit(f"{settings.RATE_LIMIT_PER_HOUR}/hour")
async def generate_report(
    request: Request,
    report_type: str = Form(...),
    brand_name: str = Form(None),
    brand_url: str = Form(None),
    competitors: str = Form(None),
    person_name: str = Form(None),
    person_role: str = Form(None),
    company_name: str = Form(None),
    industry_name: str = Form(None),
    audience_name: str = Form(None),
    geography: str = Form("US"),
    files: List[UploadFile] = File(default=[])
):
    """
    Main streaming endpoint for report generation.
    Returns NDJSON stream with progress updates and final result.
    """

    async def event_generator():
        workflow_id = None

        try:
            valid_types = ["brand_audit", "meeting_brief", "industry_profile",
                          "brand_house", "four_cs", "competitive_landscape", "audience_profile"]
            if report_type not in valid_types:
                yield json.dumps(ErrorResponse(
                    message=f"Invalid report type: {report_type}",
                    details=f"Must be one of: {', '.join(valid_types)}"
                ).model_dump(mode='json')) + "\n"
                return

            # Build initial state based on report type
            state = {"report_type": report_type, "geography": geography}

            if report_type == "brand_audit":
                if not brand_name or not brand_url:
                    yield json.dumps(ErrorResponse(
                        message="Missing required fields",
                        details="brand_name and brand_url are required"
                    ).model_dump(mode='json')) + "\n"
                    return
                state.update({
                    "brand_name": brand_name,
                    "brand_url": brand_url,
                    "competitors": [c.strip() for c in competitors.split(",") if c.strip()] if competitors else [],
                    "pdf_context": ""
                })
                if files:
                    yield json.dumps(ProgressUpdate(
                        message="Processing uploaded documents...",
                        progress_percent=5
                    ).model_dump(mode='json')) + "\n"
                    try:
                        from uuid import uuid4
                        rag_service = RAGService(str(uuid4()))
                        state["pdf_context"] = await rag_service.ingest_pdfs(files, brand_name)
                    except Exception as e:
                        logger.error("pdf_processing_failed", error=str(e))

            elif report_type == "meeting_brief":
                if not person_name or not person_role or not company_name:
                    yield json.dumps(ErrorResponse(
                        message="Missing required fields",
                        details="person_name, person_role, and company_name are required"
                    ).model_dump(mode='json')) + "\n"
                    return
                state.update({
                    "person_name": person_name,
                    "person_role": person_role,
                    "company_name": company_name
                })

            elif report_type == "industry_profile":
                if not industry_name:
                    yield json.dumps(ErrorResponse(
                        message="Missing required fields",
                        details="industry_name is required"
                    ).model_dump(mode='json')) + "\n"
                    return
                state["industry_name"] = industry_name

            elif report_type in ["brand_house", "four_cs", "competitive_landscape"]:
                if not brand_name or not brand_url:
                    yield json.dumps(ErrorResponse(
                        message="Missing required fields",
                        details="brand_name and brand_url are required"
                    ).model_dump(mode='json')) + "\n"
                    return
                state.update({"brand_name": brand_name, "brand_url": brand_url})

            elif report_type == "audience_profile":
                if not audience_name:
                    yield json.dumps(ErrorResponse(
                        message="Missing required fields",
                        details="audience_name is required"
                    ).model_dump(mode='json')) + "\n"
                    return
                state["audience_name"] = audience_name

            # Get workflow for report type (lazy initialization)
            workflow = await _get_workflow(report_type)
            if not workflow:
                yield json.dumps(ErrorResponse(
                    message="Workflow not initialized",
                    details=f"{report_type} workflow failed to initialize"
                ).model_dump(mode='json')) + "\n"
                return

            # Stream workflow execution
            logger.info("starting_workflow", report_type=report_type)
            started_at = datetime.now(tz=None)

            from uuid import uuid4
            thread_id = str(uuid4())

            async for event in workflow.astream(
                state,
                config={"configurable": {"thread_id": thread_id}}
            ):
                for node_name, state_updates in event.items():
                    if not workflow_id and "workflow_id" in state_updates:
                        workflow_id = state_updates["workflow_id"]

                    if "current_step" in state_updates:
                        yield json.dumps(ProgressUpdate(
                            message=state_updates["current_step"],
                            step=node_name,
                            progress_percent=state_updates.get("progress_percent")
                        ).model_dump(mode='json')) + "\n"

                    if "final_report" in state_updates and state_updates["final_report"]:
                        duration = (datetime.now(tz=None) - started_at).total_seconds()
                        yield json.dumps(ResultResponse(
                            markdown=state_updates["final_report"],
                            chart=state_updates.get("chart_json"),
                            metadata={
                                "workflow_id": workflow_id or "unknown",
                                "duration_seconds": duration,
                                "report_type": report_type
                            }
                        ).model_dump(mode='json')) + "\n"
                        return

        except Exception as e:
            logger.error("report_generation_failed", error=str(e))
            yield json.dumps(ErrorResponse(
                message="Report generation failed",
                details=str(e)
            ).model_dump(mode='json')) + "\n"

    return StreamingResponse(
        event_generator(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


async def _get_workflow(report_type: str):
    """Get or create workflow for report type with thread-safe initialization."""
    async with _workflow_lock:
        if report_type == "brand_audit":
            import app.graph.workflows.brand_audit_workflow as m
            if m.brand_audit_workflow is None:
                from ..graph.workflows.brand_audit_workflow import create_brand_audit_workflow
                m.brand_audit_workflow = await create_brand_audit_workflow()
            return m.brand_audit_workflow

        elif report_type == "meeting_brief":
            import app.graph.workflows.meeting_brief_workflow as m
            if m.meeting_brief_workflow is None:
                from ..graph.workflows.meeting_brief_workflow import create_meeting_brief_workflow
                m.meeting_brief_workflow = await create_meeting_brief_workflow()
            return m.meeting_brief_workflow

        elif report_type == "industry_profile":
            import app.graph.workflows.industry_workflow as m
            if m.industry_profile_workflow is None:
                from ..graph.workflows.industry_workflow import create_industry_profile_workflow
                m.industry_profile_workflow = await create_industry_profile_workflow()
            return m.industry_profile_workflow

        elif report_type == "brand_house":
            import app.graph.workflows.brand_house_workflow as m
            if m.brand_house_workflow is None:
                from ..graph.workflows.brand_house_workflow import create_brand_house_workflow
                m.brand_house_workflow = await create_brand_house_workflow()
            return m.brand_house_workflow

        elif report_type == "four_cs":
            import app.graph.workflows.four_cs_workflow as m
            if m.four_cs_workflow is None:
                from ..graph.workflows.four_cs_workflow import create_four_cs_workflow
                m.four_cs_workflow = await create_four_cs_workflow()
            return m.four_cs_workflow

        elif report_type == "competitive_landscape":
            import app.graph.workflows.competitive_landscape_workflow as m
            if m.competitive_landscape_workflow is None:
                from ..graph.workflows.competitive_landscape_workflow import create_competitive_landscape_workflow
                m.competitive_landscape_workflow = await create_competitive_landscape_workflow()
            return m.competitive_landscape_workflow

        elif report_type == "audience_profile":
            import app.graph.workflows.audience_profile_workflow as m
            if m.audience_profile_workflow is None:
                from ..graph.workflows.audience_profile_workflow import create_audience_profile_workflow
                m.audience_profile_workflow = await create_audience_profile_workflow()
            return m.audience_profile_workflow

        return None


@router.get("/workflow/{workflow_id}")
async def get_workflow_status(workflow_id: str):
    """Check status of a running workflow."""
    return {
        "workflow_id": workflow_id,
        "status": "unknown",
        "message": "Workflow status checking not yet implemented"
    }


@router.get("/cache/stats")
async def get_cache_stats():
    """Get cache statistics."""
    from ..services.cache import query_cache
    try:
        return query_cache.get_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cache/clear-expired")
async def clear_expired_cache():
    """Clear expired cache entries."""
    from ..services.cache import query_cache
    try:
        return {"cleared": query_cache.clear_expired()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
