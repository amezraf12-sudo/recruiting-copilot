from pydantic import BaseModel


class UsageInfo(BaseModel):
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
