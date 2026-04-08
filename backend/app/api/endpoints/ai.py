from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import uuid

from app.api.deps import get_current_user
from app.db.session import get_db
from app.db.models import User, Report
from app.agents.extractor import process_report_file
from app.agents.rag_pipeline import embed_and_store
from app.agents.report_analyzer import analyze_report, query_report

router = APIRouter()

class AnalyzeRequest(BaseModel):
    report_id: str

class QueryRequest(BaseModel):
    report_id: str
    question: str

@router.post("/analyze-report", response_model=Dict[str, Any])
async def api_analyze_report(
    payload: AnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        report_uuid = uuid.UUID(payload.report_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid report_id format.")

    # 1. Verify Report Access
    result = await db.execute(select(Report).where(
        Report.id == report_uuid, 
        Report.user_id == current_user.id
    ))
    report = result.scalars().first()
    
    if not report:
        raise HTTPException(status_code=404, detail="Report not found or access denied.")
        
    # 2. Extract Document Text via Fast PyMuPDF/Tesseract Engine
    try:
        extracted_text = process_report_file(report.file_url, file_type=report.file_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract document text: {e}")
        
    # 3. Store text embeddings silently inside Local FAISS DB
    try:
        embed_and_store(report_id=payload.report_id, text=extracted_text)
    except Exception as e:
        print(f"Warning: Chunking and Embedding failed cleanly - {e}")

    # 4. CRITICAL Update: Trigger structured Analytics Extractor!
    # Safeguard Context limit for Local LLMs
    safe_text = extracted_text[:14000] 
    
    from app.analytics.metrics_extractor import extract_and_store_metrics
    try:
        await extract_and_store_metrics(db, str(report_uuid), str(current_user.id), safe_text)
    except Exception as e:
        print(f"Warning: Structured analytics metric extraction failed - {e}")

    # 5. Generate primary AI Medical Summary 
    try:
        analysis_result = await analyze_report(safe_text)
        return analysis_result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI Analysis failed: {e}")


@router.post("/query-report")
async def api_query_report(
    payload: QueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        report_uuid = uuid.UUID(payload.report_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid report_id format.")
        
    result = await db.execute(select(Report).where(Report.id == report_uuid, Report.user_id == current_user.id))
    report = result.scalars().first()
    
    if not report:
        raise HTTPException(status_code=404, detail="Report not found or access denied.")
        
    try:
        answer = await query_report(report_id=payload.report_id, question=payload.question)
        return {"answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI RAG Query failed: {e}")

@router.get("/health-insights")
async def api_health_insights(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Personalized health insights: trend analysis + reference range checks
    + LLM-generated narrative, all validated via Pydantic.
    """
    from app.analytics.personalized_insights import generate_personalized_insights
    try:
        return await generate_personalized_insights(db, str(current_user.id))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Personalized insights failed: {e}")

# ========================================================
# PHASE 5: ORCHESTRATOR ROUTES (UPGRADED ARCHITECTURE)
# ========================================================

@router.post("/process-report", response_model=Dict[str, Any])
async def api_process_report(
    payload: AnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Phase 5 Orchestrated Workflow: Replaces legacy analyze-report.
    Uses the Multi-Agent Hivemind to process reports comprehensively.
    """
    from app.agents.orchestrator import orchestrator
    
    try:
        report_uuid = uuid.UUID(payload.report_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid report_id format.")

    # 1. Verify Authentication Access
    result = await db.execute(select(Report).where(Report.id == report_uuid, Report.user_id == current_user.id))
    report = result.scalars().first()
    
    if not report:
        raise HTTPException(status_code=404, detail="Report not found or access denied.")
        
    # 2. Extract Document Physics
    try:
        extracted_text = process_report_file(report.file_url, file_type=report.file_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction core failed: {e}")
        
    # 3. Store FAISS vector graph
    try:
        embed_and_store(report_id=payload.report_id, text=extracted_text)
    except Exception as e:
        print(f"Warning: FAISS chunking node failed: {e}")

    # 4. Fire Phase 3 Time-series Extractor globally
    # Safeguard Context limits specifically for Local LLM pipelines
    safe_text = extracted_text[:14000]

    from app.analytics.metrics_extractor import extract_and_store_metrics
    try:
        await extract_and_store_metrics(db, str(report_uuid), str(current_user.id), safe_text)
    except Exception as e:
        print(f"Warning: Structured SQL extraction failed - {e}")

    # 5. INITIALIZE MULTI-AGENT STATE GRAPH
    initial_state = {
        "report_text": safe_text,
        "report_id": payload.report_id,
        "user_id": str(current_user.id),
        "db": db # Safe to inject into scoped background graph dynamically
    }
    
    try:
        # Offload 100% of reasoning completely to the Orchestrator network
        final_state = await orchestrator.process_event("PROCESS_REPORT", initial_state)
        
        # Strip un-serializable db objects before responding back via REST JSON over HTTP
        if "db" in final_state:
            del final_state["db"]
            
        return final_state
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent Graph Orchestrator kernel failed: {e}")


@router.post("/agent-query")
async def api_agent_query(
    payload: QueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Phase 5 Orchestrated User RAG QA Pipeline."""
    from app.agents.orchestrator import orchestrator
    
    initial_state = {
        "report_id": payload.report_id,
        "question": payload.question
    }
    
    try:
        final_state = await orchestrator.process_event("USER_QUERY", initial_state)
        return {"answer": final_state.get("answer", "No answer found by the graph.")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query workflow graph failed: {e}")


# ========================================================
# EXPLAINABILITY — "Why did the AI decide this?"
# ========================================================

class ExplainRequest(BaseModel):
    report_id: str
    question: str   # e.g. "Why was my risk level High?"

@router.post("/explain")
async def api_explain(
    payload: ExplainRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Answers "why" questions about any AI-driven decision.
    Grounds every explanation in actual metric values and report content —
    never fabricates. Returns a validated ExplainabilityOutput.
    """
    from app.agents.explainability import explain

    try:
        report_uuid = uuid.UUID(payload.report_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid report_id format.")

    result = await db.execute(
        select(Report).where(Report.id == report_uuid, Report.user_id == current_user.id)
    )
    if not result.scalars().first():
        raise HTTPException(status_code=404, detail="Report not found or access denied.")

    try:
        return await explain(
            db=db,
            user_id=str(current_user.id),
            report_id=payload.report_id,
            question=payload.question,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Explainability engine failed: {e}")


# ========================================================
# HEALTH COPILOT — Cross-Report Context-Aware Chat
# ========================================================

class CopilotMessage(BaseModel):
    role: str        # "user" or "assistant"
    content: str

class CopilotRequest(BaseModel):
    question: str
    history: Optional[List[CopilotMessage]] = None

@router.post("/copilot-chat")
async def api_copilot_chat(
    payload: CopilotRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Health Copilot — context-aware chat across ALL patient reports + trends.
    Uses cross-report RAG + metric history for personalized guidance.
    """
    from app.agents.copilot import copilot_chat

    history = None
    if payload.history:
        history = [{"role": m.role, "content": m.content} for m in payload.history]

    try:
        answer = await copilot_chat(
            db=db,
            user_id=str(current_user.id),
            question=payload.question,
            conversation_history=history,
        )
        return {"answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health Copilot failed: {e}")
