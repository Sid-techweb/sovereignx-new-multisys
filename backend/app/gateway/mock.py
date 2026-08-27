from app.gateway.base import ModelGateway
from app.schemas.analysis import AnalysisRequest, AnalysisResponse

class MockGateway(ModelGateway):
    async def analyze(self, request: AnalysisRequest) -> AnalysisResponse:
        """
        Implements ModelGateway to return a static, realistic document-analysis
        response for Phase 1 testing and prototyping.
        """
        return AnalysisResponse(
            finding="Bearing housing temperature exceeds the specified SOP threshold.",
            sop_reference="Maintenance SOP Section 4.2",
            confidence=0.87,
            recommended_action="Inspect lubrication and bearing clearance."
        )

    async def generate(self, prompt: str, system_prompt: str = None) -> str:
        """
        Implements ModelGateway to return a static grounded query response
        for test/mock validation environments.
        """
        return (
            "Based on the provided maintenance records, Pump P-204 experienced "
            "abnormal housing temperatures at 12:00 UTC on August 12, 2026, "
            "as logged in [pump_P204_sensor_data.csv]."
        )

