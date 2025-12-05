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


@router.post("/generate-report")
@limiter.limit(f"{settings.RATE_LIMIT_PER_HOUR}/hour")
async def generate_report(
    request: Request,
    report_type: str = Form(...),
    # Brand Audit fields
    brand_name: str = Form(None),
    brand_url: str = Form(None),
    competitors: str = Form(None),  # Comma-separated
    # Meeting Brief fields
    person_name: str = Form(None),
    person_role: str = Form(None),
    company_name: str = Form(None),
    # Industry Profile fields
    industry_name: str = Form(None),
    # Audience Profile fields
    audience_name: str = Form(None),
    # Universal
    geography: str = Form("US"),
    files: List[UploadFile] = File(default=[])
):
    """
    Main streaming endpoint for report generation.

    Returns NDJSON stream:
    - {"type": "progress", "message": "...", "progress_percent": 20}
    - {"type": "result", "markdown": "...", "chart": {...}}
    - {"type": "error", "message": "..."}
    """

    async def event_generator():
        workflow_id = None

        try:
            # Validate report type
            valid_types = ["brand_audit", "meeting_brief", "industry_profile", "brand_house", "four_cs", "competitive_landscape", "audience_profile"]
            if report_type not in valid_types:
                yield json.dumps(ErrorResponse(
                    message=f"Invalid report type: {report_type}",
                    details=f"Must be one of: {', '.join(valid_types)}"
                ).model_dump(mode='json')) + "\n"
                return

            # Build initial state based on report type
            if report_type == "brand_audit":
                if not brand_name or not brand_url:
                    yield json.dumps(ErrorResponse(
                        message="Missing required fields",
                        details="brand_name and brand_url are required for Brand Audit"
                    ).model_dump(mode='json')) + "\n"
                    return

                state = {
                    "report_type": report_type,
                    "brand_name": brand_name,
                    "brand_url": brand_url,
                    "competitors": competitors.split(",") if competitors else [],
                    "geography": geography,
                    "workflow_id": None,  # Will be set by workflow
                    "pdf_context": ""
                }

                # Handle PDF uploads
                if files:
                    yield json.dumps(ProgressUpdate(
                        message="Processing uploaded documents...",
                        progress_percent=5
                    ).model_dump(mode='json')) + "\n"

                    try:
                        from uuid import uuid4
                        temp_workflow_id = str(uuid4())

                        rag_service = RAGService(temp_workflow_id)
                        pdf_context = await rag_service.ingest_pdfs(files, brand_name)
                        state["pdf_context"] = pdf_context

                        logger.info("pdfs_processed", count=len(files))

                    except Exception as e:
                        logger.error("pdf_processing_failed", error=str(e))
                        yield json.dumps(ProgressUpdate(
                            message="PDF processing failed, continuing without PDF context...",
                            progress_percent=5
                        ).model_dump(mode='json')) + "\n"

            elif report_type == "meeting_brief":
                if not person_name or not person_role or not company_name:
                    yield json.dumps(ErrorResponse(
                        message="Missing required fields",
                        details="person_name, person_role, and company_name are required for Meeting Brief"
                    ).model_dump(mode='json')) + "\n"
                    return

                state = {
                    "report_type": report_type,
                    "person_name": person_name,
                    "person_role": person_role,
                    "company_name": company_name,
                    "geography": geography
                }

            elif report_type == "industry_profile":
                if not industry_name:
                    yield json.dumps(ErrorResponse(
                        message="Missing required fields",
                        details="industry_name is required for Industry Profile"
                    ).model_dump(mode='json')) + "\n"
                    return

                state = {
                    "report_type": report_type,
                    "industry_name": industry_name,
                    "geography": geography
                }

            elif report_type == "brand_house":
                if not brand_name or not brand_url:
                    yield json.dumps(ErrorResponse(
                        message="Missing required fields",
                        details="brand_name and brand_url are required for Brand House"
                    ).model_dump(mode='json')) + "\n"
                    return

                state = {
                    "report_type": report_type,
                    "brand_name": brand_name,
                    "brand_url": brand_url,
                    "geography": geography
                }

            elif report_type == "four_cs":
                if not brand_name or not brand_url:
                    yield json.dumps(ErrorResponse(
                        message="Missing required fields",
                        details="brand_name and brand_url are required for Four C's Analysis"
                    ).model_dump(mode='json')) + "\n"
                    return

                state = {
                    "report_type": report_type,
                    "brand_name": brand_name,
                    "brand_url": brand_url,
                    "geography": geography
                }

            elif report_type == "competitive_landscape":
                if not brand_name or not brand_url:
                    yield json.dumps(ErrorResponse(
                        message="Missing required fields",
                        details="brand_name and brand_url are required for Competitive Landscape"
                    ).model_dump(mode='json')) + "\n"
                    return

                state = {
                    "report_type": report_type,
                    "brand_name": brand_name,
                    "brand_url": brand_url,
                    "geography": geography
                }

            elif report_type == "audience_profile":
                if not audience_name:
                    yield json.dumps(ErrorResponse(
                        message="Missing required fields",
                        details="audience_name is required for Audience Profile"
                    ).model_dump(mode='json')) + "\n"
                    return

                state = {
                    "report_type": report_type,
                    "audience_name": audience_name,
                    "geography": geography
                }

            # Get workflow for report type (with lazy initialization)
            if report_type == "brand_audit":
                import app.graph.workflows.brand_audit_workflow as ba_module
                if ba_module.brand_audit_workflow is None:
                    logger.info("lazy_initializing_brand_audit_workflow")
                    from ..graph.workflows.brand_audit_workflow import create_brand_audit_workflow
                    ba_module.brand_audit_workflow = await create_brand_audit_workflow()
                workflow = ba_module.brand_audit_workflow

            elif report_type == "meeting_brief":
                import app.graph.workflows.meeting_brief_workflow as mb_module
                if mb_module.meeting_brief_workflow is None:
                    logger.info("lazy_initializing_meeting_brief_workflow")
                    from ..graph.workflows.meeting_brief_workflow import create_meeting_brief_workflow
                    mb_module.meeting_brief_workflow = await create_meeting_brief_workflow()
                workflow = mb_module.meeting_brief_workflow

            elif report_type == "industry_profile":
                import app.graph.workflows.industry_workflow as ip_module
                if ip_module.industry_profile_workflow is None:
                    logger.info("lazy_initializing_industry_profile_workflow")
                    from ..graph.workflows.industry_workflow import create_industry_profile_workflow
                    ip_module.industry_profile_workflow = await create_industry_profile_workflow()
                workflow = ip_module.industry_profile_workflow

            elif report_type == "brand_house":
                import app.graph.workflows.brand_house_workflow as bh_module
                if bh_module.brand_house_workflow is None:
                    logger.info("lazy_initializing_brand_house_workflow")
                    from ..graph.workflows.brand_house_workflow import create_brand_house_workflow
                    bh_module.brand_house_workflow = await create_brand_house_workflow()
                workflow = bh_module.brand_house_workflow

            elif report_type == "four_cs":
                import app.graph.workflows.four_cs_workflow as fc_module
                if fc_module.four_cs_workflow is None:
                    logger.info("lazy_initializing_four_cs_workflow")
                    from ..graph.workflows.four_cs_workflow import create_four_cs_workflow
                    fc_module.four_cs_workflow = await create_four_cs_workflow()
                workflow = fc_module.four_cs_workflow

            elif report_type == "competitive_landscape":
                import app.graph.workflows.competitive_landscape_workflow as cl_module
                if cl_module.competitive_landscape_workflow is None:
                    logger.info("lazy_initializing_competitive_landscape_workflow")
                    from ..graph.workflows.competitive_landscape_workflow import create_competitive_landscape_workflow
                    cl_module.competitive_landscape_workflow = await create_competitive_landscape_workflow()
                workflow = cl_module.competitive_landscape_workflow

            elif report_type == "audience_profile":
                import app.graph.workflows.audience_profile_workflow as ap_module
                if ap_module.audience_profile_workflow is None:
                    logger.info("lazy_initializing_audience_profile_workflow")
                    from ..graph.workflows.audience_profile_workflow import create_audience_profile_workflow
                    ap_module.audience_profile_workflow = await create_audience_profile_workflow()
                workflow = ap_module.audience_profile_workflow

            else:
                yield json.dumps(ErrorResponse(
                    message="Invalid report type",
                    details=f"Unknown report type: {report_type}"
                ).model_dump(mode='json')) + "\n"
                return

            if not workflow:
                yield json.dumps(ErrorResponse(
                    message="Workflow not initialized",
                    details=f"{report_type} workflow failed to initialize. Please contact support."
                ).model_dump(mode='json')) + "\n"
                return

            # Stream workflow execution
            logger.info(
                "starting_workflow",
                report_type=report_type,
                state_keys=list(state.keys()),
                state=state
            )

            started_at = datetime.utcnow()

            # Generate workflow ID for this execution
            from uuid import uuid4
            thread_id = str(uuid4())

            async for event in workflow.astream(
                state,
                config={"configurable": {"thread_id": thread_id}}
            ):
                # LangGraph yields dict of {node_name: state_updates}
                for node_name, state_updates in event.items():
                    logger.debug("workflow_event", node=node_name, updates=list(state_updates.keys()))

                    # Extract workflow ID
                    if not workflow_id and "workflow_id" in state_updates:
                        workflow_id = state_updates["workflow_id"]

                    # Send progress update
                    if "current_step" in state_updates:
                        yield json.dumps(ProgressUpdate(
                            message=state_updates["current_step"],
                            step=node_name,
                            progress_percent=state_updates.get("progress_percent")
                        ).model_dump(mode='json')) + "\n"

                    # Check for completion
                    if "final_report" in state_updates and state_updates["final_report"]:
                        duration = (datetime.utcnow() - started_at).total_seconds()

                        # Final result
                        yield json.dumps(ResultResponse(
                            markdown=state_updates["final_report"],
                            chart=state_updates.get("chart_json"),
                            metadata={
                                "workflow_id": workflow_id or "unknown",
                                "duration_seconds": duration,
                                "report_type": report_type,
                                "geography": geography
                            }
                        ).model_dump(mode='json')) + "\n"

                        logger.info(
                            "workflow_complete",
                            report_type=report_type,
                            duration=duration,
                            workflow_id=workflow_id
                        )
                        return

        except Exception as e:
            logger.error("report_generation_failed", error=str(e), report_type=report_type)
            error_response = ErrorResponse(
                message="Report generation failed",
                details=str(e)
            )
            yield error_response.model_dump_json() + "\n"

    return StreamingResponse(
        event_generator(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@router.get("/workflow/{workflow_id}")
async def get_workflow_status(workflow_id: str):
    """
    Check status of a running workflow.
    Useful if user refreshes page during generation.
    """
    # TODO: Implement workflow status check via PostgreSQL
    # For now, return not implemented
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
        stats = query_cache.get_stats()
        return stats
    except Exception as e:
        logger.error("cache_stats_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cache/clear-expired")
async def clear_expired_cache():
    """Clear expired cache entries."""
    from ..services.cache import query_cache

    try:
        cleared = query_cache.clear_expired()
        return {"cleared": cleared}
    except Exception as e:
        logger.error("cache_clear_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
