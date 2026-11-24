from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Any, List, Optional
import uuid

from app.api.deps import get_current_user
from app.db.session import get_db
from app.db.models import User, Report
from app.schemas.report import ReportResponse
from app.services.upload import detect_file_type, remove_stored_file, save_upload_file

router = APIRouter()

@router.post("/upload", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def upload_report(
    file: UploadFile = File(...),
    # Kept for backwards compatibility with older clients; the server now
    # derives the type from the validated file extension instead of trusting it.
    file_type: Optional[str] = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    _, detected_type = detect_file_type(file.filename)

    # Validate + save physical file to disk
    file_path = await save_upload_file(file)

    # Save record metadata to PostgreSQL database
    report = Report(
        user_id=current_user.id,
        file_url=file_path,
        file_type=detected_type
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    
    return report

@router.get("/my-reports", response_model=List[ReportResponse])
async def get_my_reports(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    result = await db.execute(select(Report).where(Report.user_id == current_user.id))
    reports = result.scalars().all()
    # Ensure it returns as a proper list mapping to schemas
    return list(reports)

@router.get("/compare/{report_id}")
async def compare_report(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    from app.analytics.comparison_engine import compare_report_metrics
    try:
        comparisons = await compare_report_metrics(db, report_id, str(current_user.id))
        return comparisons
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Comparison engine failed: {e}")

@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> None:
    try:
        report_uuid = uuid.UUID(report_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid report ID format.")
    
    result = await db.execute(
        select(Report).where(Report.id == report_uuid, Report.user_id == current_user.id)
    )
    report = result.scalars().first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found or access denied.")
    
    file_path = report.file_url
    await db.delete(report)
    await db.commit()

    # Clean up artefacts outside the database so deleted reports don't
    # linger on disk or keep surfacing in RAG / Copilot answers.
    remove_stored_file(file_path)
    try:
        from app.agents.rag_pipeline import delete_report_vectors
        delete_report_vectors(str(report_uuid))
    except Exception as e:
        print(f"Warning: could not remove FAISS vectors for report {report_uuid}: {e}")
