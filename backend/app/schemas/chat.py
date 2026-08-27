from pydantic import BaseModel

class ChatRequest(BaseModel):
    prompt: str

class ChatResponse(BaseModel):
    finding: str
    sop_reference: str
    confidence: float
    recommended_action: str
