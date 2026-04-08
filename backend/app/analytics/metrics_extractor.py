import json
import logging
import uuid
from typing import List, Dict, Any
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.db.models import HealthMetric

logger = logging.getLogger(__name__)

# Initialize secure async OpenAI Client
try:
    openai_client = AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY or "lm-studio",
        base_url=settings.OPENAI_API_BASE or "http://localhost:1234/v1"
    )
except Exception as e:
    logger.error(f"Failed to initialize OpenAI client: {e}")
    openai_client = None

async def extract_and_store_metrics(
    db: AsyncSession, 
    report_id: str, 
    user_id: str, 
    report_text: str
) -> List[HealthMetric]:
    """
    Extracts structured health metrics using OpenAI's JSON mode, formats them into exact 
    float types, and inserts them automatically into the PostgreSQL database.
    """
    if not openai_client:
        logger.warning("OpenAI client not configured; skipping metrics extraction.")
        return []

    system_prompt = (
        "You are an expert clinical data extractor. "
        "Your goal is to extract strictly quantitative medical metrics from the text. "
        "Focus specifically on: Hemoglobin, Glucose, Creatinine, and Blood Pressure. "
        "Return a JSON object containing a single key called 'metrics' "
        "which is a list of objects. Each object must have exactly three keys: "
        "'name' (lowercase string, e.g., 'glucose', 'hemoglobin', 'creatinine'), "
        "'value' (Float number strictly), "
        "'unit' (string, e.g., 'mg/dL', 'g/dL'). "
        "If Blood Pressure is identified (e.g. 120/80), you MUST separate it into TWO objects: "
        "one named 'blood_pressure_systolic' (value: 120.0, unit 'mmHg') and "
        "one named 'blood_pressure_diastolic' (value: 80.0, unit 'mmHg'). "
        "If a metric is not present in the text, omit it. "
        "Return {\"metrics\": []} if no relevant metrics exist.\n"
    )

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Extracted Medical Text:\n{report_text}"}
            ],
            temperature=0.1, # Extremely strict analytical extraction
        )
        
        result_content = response.choices[0].message.content
        start = result_content.find('{')
        end = result_content.rfind('}')
        if start != -1 and end != -1:
            result_content = result_content[start:end+1]
            
        parsed = json.loads(result_content)
        metrics_list = parsed.get("metrics", [])
        
        stored_metrics = []
        
        for item in metrics_list:
            # Safely cast and validate the float conversion
            try:
                val_float = float(item.get("value"))
            except (ValueError, TypeError):
                continue # Skip corrupt metrics
                
            metric_record = HealthMetric(
                report_id=uuid.UUID(report_id),
                user_id=uuid.UUID(user_id),
                metric_name=item.get("name", "unknown").lower(),
                metric_value=val_float,
                unit=item.get("unit", "")
            )
            db.add(metric_record)
            stored_metrics.append(metric_record)
            
        if stored_metrics:
            await db.commit()
            
        logger.info(f"Successfully extracted and stored {len(stored_metrics)} metrics.")
        return stored_metrics
        
    except Exception as e:
        logger.error(f"Failed to extract and store metrics through OpenAI: {e}")
        return []
