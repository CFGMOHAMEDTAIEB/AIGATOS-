import time
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.llm_config import LLMConfigurationError, load_llm_settings, safe_settings
from app.llm_providers import LLMAuthenticationError, LLMError, LLMPermissionError, get_provider

router=APIRouter(prefix="/api/v1/llm",tags=["llm-diagnostics"])


class ProbeOutput(BaseModel):
    ok: Literal[True]


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    provider: str
    model: str
    reply: str


def _base(settings):
    return {**safe_settings(settings),"reachable":False,"authorized":False,"latency_ms":None,"structured_output_supported":False,"error_code":None}


@router.get("/status")
def status()->dict:
    try:
        settings=load_llm_settings();return _base(settings)
    except LLMConfigurationError:
        return {"provider":None,"model":None,"hostname":"","configured":False,"reachable":False,"authorized":False,"latency_ms":None,"structured_output_supported":False,"error_code":"LLM_CONFIGURATION_ERROR"}


@router.post("/test")
def test_provider()->dict:
    try: settings=load_llm_settings()
    except LLMConfigurationError:
        return {"configured":False,"reachable":False,"authorized":False,"latency_ms":None,"structured_output_supported":False,"error_code":"LLM_CONFIGURATION_ERROR","provider":None,"model":None}
    result=_base(settings)
    if not settings.configured:
        result["error_code"]="LLM_NOT_CONFIGURED";return result
    started=time.perf_counter()
    try:
        _,probe=get_provider(settings).generate_structured("Return only a JSON object matching the supplied schema.","Connectivity probe: return {\"ok\": true}.",ProbeOutput)
        result.update(reachable=True,authorized=True,structured_output_supported=probe.ok)
    except LLMError as error:
        result["error_code"]=error.code
        result["reachable"]=error.code not in {"LLM_CONNECT_TIMEOUT","LLM_CONNECTION_FAILED","LLM_PROXY_ERROR","LLM_UNAVAILABLE"}
        result["authorized"]=not isinstance(error,(LLMAuthenticationError,LLMPermissionError)) and result["reachable"]
    result["latency_ms"]=round((time.perf_counter()-started)*1000)
    return result


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    """Text-only assistant; it has no tools or access to business operations."""
    try:
        settings=load_llm_settings()
    except LLMConfigurationError:
        raise HTTPException(status_code=503,detail={"code":"LLM_CONFIGURATION_ERROR","message":"Le fournisseur LLM n’est pas configuré."})
    if not settings.configured:
        raise HTTPException(status_code=503,detail={"code":"LLM_NOT_CONFIGURED","message":"Le fournisseur LLM n’est pas configuré."})
    try:
        result=get_provider(settings).generate_text(
            "You are the AIGATOS assistant. Reply in French, clearly and concisely. "
            "You have no access to application data and cannot execute tools, actions, "
            "approvals, simulations, or vehicle operations. Never claim otherwise.",
            payload.prompt.strip(),
        )
    except LLMError as error:
        raise HTTPException(status_code=502,detail=error.public()) from error
    return ChatResponse(provider=settings.provider or "",model=settings.model or "",reply=result.content)
