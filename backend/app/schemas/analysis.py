from pydantic import BaseModel, Field

class AnalysisRequest(BaseModel):
    input_text: str = Field(..., description="The inspection text or findings to analyze")

class AnalysisResponse(BaseModel):
    finding: str
    sop_reference: str
    confidence: float
    recommended_action: str
