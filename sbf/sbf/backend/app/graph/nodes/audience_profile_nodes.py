"""
Audience Profile workflow nodes.
Demographics and psychographics analysis using GPT-5.1 knowledge only.
"""

from typing import Dict, Any
import traceback
import structlog

from ...models.schemas import StepStatus

logger = structlog.get_logger()


async def node_analyze_audience_profile(state: Dict[str, Any]) -> Dict[str, Any]:
    """Generate comprehensive audience profile using GPT-5.1 knowledge."""
    from ...core.llm_client import LLMClient
    from ...graph.prompts import AUDIENCE_PROFILE_PROMPT

    audience_name = state.get("audience_name", "")
    geography = state.get("geography", "US")

    # Build prompt
    prompt = AUDIENCE_PROFILE_PROMPT.format(
        audience_name=audience_name,
        geography=geography,
        context=""  # No scraped context for audience profiles
    )

    try:
        llm = LLMClient()
        report, meta = llm.generate(
            key_name=f"audience_profile_{audience_name}",
            prompt=prompt
        )

        # Generate radar chart data for audience priorities
        chart_prompt = f"""Based on the audience profile for "{audience_name}" in {geography}, create a radar chart showing their priorities.

Return ONLY a JSON object:
{{
    "chart_type": "radar",
    "chart_title": "Audience Priorities: {audience_name}",
    "data": [
        {{"subject": "Priority Name", "value": 85, "fullMark": 100}}
    ]
}}

Include 6-8 key priorities with values from 0-100."""

        chart_response, _ = llm.generate(
            key_name=f"audience_chart_{audience_name}",
            prompt=chart_prompt,
            force_json=True
        )

        import json
        chart_json = json.loads(chart_response.strip())

        logger.info(
            "audience_profile_generated",
            audience=audience_name,
            report_length=len(report),
            tokens=meta.get("token_usage", 0)
        )

        return {
            **state,
            "final_report": report,
            "chart_json": chart_json,
            "current_step": "Audience profile complete...",
            "progress_percent": 90,
            "steps": {**state.get("steps", {}), "analyze": StepStatus.COMPLETED.value}
        }

    except Exception as e:
        logger.error(
            "audience_profile_generation_failed",
            audience=audience_name,
            error=str(e),
            traceback=traceback.format_exc()
        )
        return {
            **state,
            "final_report": f"# Audience Profile: {audience_name}\n\nProfile generation failed. Please try again.\n\nError: {str(e)}",
            "errors": state.get("errors", []) + [f"Profile generation failed: {str(e)}"],
            "current_step": "Profile generation failed",
            "progress_percent": 90,
            "steps": {**state.get("steps", {}), "analyze": StepStatus.FAILED.value}
        }


# Backward compatible alias
node_audience_analysis = node_analyze_audience_profile
