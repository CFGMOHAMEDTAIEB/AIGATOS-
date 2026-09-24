"""Typed, secret-safe adapters for OpenAI-compatible LLM providers."""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, TypeVar

from pydantic import BaseModel, ValidationError

from app.llm_config import LLMSettings

T=TypeVar("T",bound=BaseModel)


@dataclass(frozen=True)
class ProviderResult:
    content: str
    prompt_tokens: int | None=None
    completion_tokens: int | None=None
    total_tokens: int | None=None
    attempt_count: int=1


class LLMError(RuntimeError):
    code="LLM_ERROR";message="Le fournisseur LLM a échoué.";retryable=False
    def __init__(self, provider: str|None=None, model: str|None=None):
        super().__init__(self.message);self.provider=provider;self.model=model;self.attempt_count=1
    def public(self)->dict:
        return {"code":self.code,"message":self.message,"provider":self.provider,"model":self.model,"retryable":self.retryable}
class LLMAuthenticationError(LLMError): code="LLM_AUTHENTICATION_FAILED";message="La clé du fournisseur est absente ou invalide."
class LLMPermissionError(LLMError): code="LLM_PERMISSION_DENIED";message="Le fournisseur refuse l’accès au modèle configuré."
class LLMModelNotFoundError(LLMError): code="LLM_MODEL_NOT_FOUND";message="Le modèle configuré est introuvable chez le fournisseur."
class LLMRateLimitError(LLMError): code="LLM_RATE_LIMITED";message="La limite du fournisseur a été atteinte.";retryable=True
class LLMConnectTimeoutError(LLMError): code="LLM_CONNECT_TIMEOUT";message="La connexion au fournisseur a expiré.";retryable=True
class LLMReadTimeoutError(LLMError): code="LLM_READ_TIMEOUT";message="Le fournisseur n’a pas répondu dans le délai de lecture.";retryable=True
class LLMConnectionError(LLMError): code="LLM_CONNECTION_FAILED";message="La connexion au fournisseur LLM a échoué."
class LLMProxyError(LLMError): code="LLM_PROXY_ERROR";message="Le proxy configuré empêche la connexion au fournisseur LLM."
class LLMInvalidResponseError(LLMError): code="LLM_INVALID_RESPONSE";message="La réponse du fournisseur est vide ou incompatible."
class LLMValidationError(LLMError): code="LLM_VALIDATION_FAILED";message="La réponse structurée ne respecte pas le schéma attendu."
class LLMUnavailableError(LLMError): code="LLM_UNAVAILABLE";message="Le fournisseur LLM est temporairement indisponible.";retryable=True
class LLMRequestError(LLMError): code="LLM_BAD_REQUEST";message="La requête a été refusée comme invalide."


class LLMProvider(ABC):
    settings: LLMSettings
    def health_check(self)->dict:
        started=time.perf_counter();models=self.list_models()
        return {"reachable":True,"authorized":True,"latency_ms":round((time.perf_counter()-started)*1000),"model_available":self.settings.model in models if models else None}
    def list_models(self)->list[str]:
        return []
    @abstractmethod
    def generate(self,system_prompt:str,user_prompt:str)->ProviderResult: raise NotImplementedError
    def generate_structured(self,system_prompt:str,user_prompt:str,output_model:type[T])->tuple[ProviderResult,T]:
        schema=json.dumps(output_model.model_json_schema(),ensure_ascii=False)
        result=self.generate(system_prompt+"\nReturn JSON matching this schema exactly:\n"+schema,user_prompt)
        provider=getattr(self,"settings",None).provider if getattr(self,"settings",None) else None
        model=getattr(self,"settings",None).model if getattr(self,"settings",None) else None
        try: payload=json.loads(result.content)
        except (json.JSONDecodeError,TypeError) as error: raise LLMInvalidResponseError(provider,model) from error
        try: value=output_model.model_validate(payload)
        except ValidationError as error: raise LLMValidationError(provider,model) from error
        return result,value
    def normalize_error(self,error:Exception)->LLMError:
        return normalize_error(error,getattr(self,"settings",None))


def normalize_error(error:Exception,settings:LLMSettings|None=None)->LLMError:
    provider=settings.provider if settings else None;model=settings.model if settings else None
    if isinstance(error,LLMError): return error
    status=getattr(error,"status_code",None) or getattr(getattr(error,"response",None),"status_code",None)
    mapping={400:LLMRequestError,401:LLMAuthenticationError,403:LLMPermissionError,404:LLMModelNotFoundError,429:LLMRateLimitError}
    if status in mapping: return mapping[status](provider,model)
    if status and status>=500: return LLMUnavailableError(provider,model)
    chain=[];current:BaseException|None=error
    while current is not None and current not in chain:
        chain.append(current);current=current.__cause__ or current.__context__
    names=" ".join(type(item).__name__.lower() for item in chain)
    if "proxyerror" in names: return LLMProxyError(provider,model)
    if "connecttimeout" in names: return LLMConnectTimeoutError(provider,model)
    if "readtimeout" in names or "apitimeout" in names or isinstance(error,TimeoutError): return LLMReadTimeoutError(provider,model)
    if "connecterror" in names or "connectionerror" in names: return LLMConnectionError(provider,model)
    if "json" in names or "validation" in names: return LLMInvalidResponseError(provider,model)
    return LLMRequestError(provider,model)


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self,settings:LLMSettings,client=None,sleeper:Callable[[float],None]=time.sleep):
        self.settings=settings;self.sleeper=sleeper
        if client is None:
            import httpx
            from openai import OpenAI
            timeout=httpx.Timeout(connect=settings.connect_timeout_seconds,read=settings.read_timeout_seconds,write=settings.write_timeout_seconds,pool=settings.pool_timeout_seconds)
            client=OpenAI(api_key=settings.api_key.get_secret_value(),base_url=settings.base_url,timeout=timeout,max_retries=0)
        self.client=client

    def list_models(self)->list[str]:
        try: return [item.id for item in self.client.models.list().data]
        except Exception as error: raise self.normalize_error(error) from error

    def _once(self,system_prompt:str,user_prompt:str,*,structured:bool=True)->ProviderResult:
        arguments={"model":self.settings.model,"messages":[{"role":"system","content":system_prompt},{"role":"user","content":user_prompt}],"temperature":min(self.settings.temperature,.2),"max_tokens":self.settings.max_output_tokens}
        if structured: arguments["response_format"]={"type":"json_object"}
        response=self.client.chat.completions.create(**arguments)
        content=response.choices[0].message.content if response.choices else None
        if not content: raise LLMInvalidResponseError(self.settings.provider,self.settings.model)
        usage=getattr(response,"usage",None)
        return ProviderResult(content=content,prompt_tokens=getattr(usage,"prompt_tokens",None),completion_tokens=getattr(usage,"completion_tokens",None),total_tokens=getattr(usage,"total_tokens",None))

    def generate(self,system_prompt:str,user_prompt:str)->ProviderResult:
        last:LLMError|None=None
        for attempt in range(1,self.settings.max_attempts+1):
            try:
                result=self._once(system_prompt,user_prompt)
                return ProviderResult(**{**result.__dict__,"attempt_count":attempt})
            except Exception as error:
                last=self.normalize_error(error)
                if not last.retryable or attempt>=self.settings.max_attempts:
                    last.attempt_count=attempt
                    raise last from error
                self.sleeper(min(.25*(2**(attempt-1)),1.0))
        raise last or LLMUnavailableError(self.settings.provider,self.settings.model)

    def generate_text(self,system_prompt:str,user_prompt:str)->ProviderResult:
        """Generate one bounded, plain-text assistant response."""
        last:LLMError|None=None
        for attempt in range(1,self.settings.max_attempts+1):
            try:
                result=self._once(system_prompt,user_prompt,structured=False)
                return ProviderResult(**{**result.__dict__,"attempt_count":attempt})
            except Exception as error:
                last=self.normalize_error(error)
                if not last.retryable or attempt>=self.settings.max_attempts:
                    last.attempt_count=attempt
                    raise last from error
                self.sleeper(min(.25*(2**(attempt-1)),1.0))
        raise last or LLMUnavailableError(self.settings.provider,self.settings.model)


class NvidiaProvider(OpenAICompatibleProvider): pass
class GoogleProvider(OpenAICompatibleProvider): pass
class DeepSeekProvider(OpenAICompatibleProvider): pass
class KimiProvider(OpenAICompatibleProvider): pass
class OpenAIProvider(OpenAICompatibleProvider): pass
class OllamaProvider(OpenAICompatibleProvider): pass

PROVIDER_REGISTRY:dict[str,Callable[[LLMSettings],LLMProvider]]={"nvidia":NvidiaProvider,"google":GoogleProvider,"openai":OpenAIProvider,"ollama":OllamaProvider,"deepseek":DeepSeekProvider,"kimi":KimiProvider}


def get_provider(settings:LLMSettings,registry:dict[str,Callable[[LLMSettings],LLMProvider]]|None=None)->LLMProvider:
    factory=(registry or PROVIDER_REGISTRY).get(settings.provider or "")
    if factory is None: raise ValueError("Unknown LLM provider")
    return factory(settings)
