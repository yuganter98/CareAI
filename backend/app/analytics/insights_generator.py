import logging
from typing import Dict, Any
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import json
import uuid

from app.core.config import settings
from app.db.models import HealthMetric

logger = logging.getLogger(__name__)

# Initialize OpenAI Client securely
try:
    openai_client = AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY or "lm-studio",
        base_url=settings.OPENAI_API_BASE or "http://localhost:1234/v1"
    )
except Exception as e:
    logger.error(f"Failed to initialize OpenAI client for insights: {e}")
    openai_client = None

async def generate_health_insights(db: AsyncSession, user_id: str) -> Dict[str, Any]:
    """
    1. Fetches the patient's entire historical metric timeline across all DB reports.
    2. Packages it into structured JSON context.
    3. Feeds it to the LLM to generate intelligent, holistic trend tracking insights.
    """
    if not openai_client:
        raise ValueError("OpenAI API Key is missing. Insights cannot be generated.")

    user_uuid = uuid.UUID(user_id)
    
    # 1. Map Time-series metric data
    result = await db.execute(
        select(HealthMetric)
        .where(HealthMetric.user_id == user_uuid)
        .order_by(HealthMetric.recorded_at.asc())
    )
    all_metrics = result.scalars().all()
    
    if not all_metrics:
        return {"insights": ["No historical health metric data available to analyze yet."]}
        
    timeline_data = {}
    for pm in all_metrics:
        if pm.metric_name not in timeline_data:
            timeline_data[pm.metric_name] = []
        
        date_str = pm.recorded_at.strftime("%Y-%m-%d")    
        timeline_data[pm.metric_name].append(
            {"date": date_str, "value": pm.metric_value, "unit": pm.unit}
        )
        
    system_prompt = (
        "You are an elite medical AI analyst. "
        "Review the structured array of historical health metrics for the patient. "
        "Your task is to identify macro-level trends and highlight exactly what is increasing, decreasing, or sitting at elevated/dangerous levels strictly over time. "
        "Provide bullet point insights describing actionable takeaways tracking their historical patterns. "
        "Format your answer ONLY as a raw JSON object with a single key 'insights' containing an array of strings. "
        "Example:\n{\n  \"insights\": [\n    \"Glucose levels are compounding dangerously high over the last 3 months.\",\n    \"Creatinine is stable at healthy levels.\"\n  ]\n}\n\n"
    )
    
    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Historical Metrics (Chronological):\n{json.dumps(timeline_data)}"}
            ],
            temperature=0.3, # Keeps the insights highly clinical and grounded
        )
        
        result_content = response.choices[0].message.content
        start = result_content.find('{')
        end = result_content.rfind('}')
        if start != -1 and end != -1:
            result_content = result_content[start:end+1]
            
        parsed = json.loads(result_content)
        
        # Attach required medical disclaimer
        if "insights" in parsed and isinstance(parsed["insights"], list):
            parsed["insights"].append("*Disclaimer: This is an AI-generated trend insight and not clinical medical advice.*")
            
        return parsed
        
    except Exception as e:
        logger.error(f"Failed to generate health insights: {e}")
        raise ValueError("Insight generator API failed internally.")
