import time
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.llm_config import LLMConfigurationError, load_llm_settings, safe_settings
from app.llm_providers import LLMAuthenticationError, LLMError, LLMPermissionError, get_provider

router=APIRouter(prefix="/api/v1/llm",tags=["llm-diagnostics"])


class ProbeOutput(BaseModel):
    ok: Literal[True]


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
