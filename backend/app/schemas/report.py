from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

class ReportResponse(BaseModel):
    id: UUID
    user_id: UUID
    file_url: str
    file_type: str
    uploaded_at: datetime
    
    class Config:
        from_attributes = True
