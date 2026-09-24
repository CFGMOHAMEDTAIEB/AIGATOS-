"""Create ignored local LLM configuration without ever printing secret values."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "secrets" / "models-api" / "glm-api.py"
TARGET = ROOT / ".env"


def _literal_secret() -> str:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8", errors="strict"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg == "api_key" and isinstance(keyword.value, ast.Constant):
                value = keyword.value.value
                if isinstance(value, str) and len(value) >= 20 and "$" not in value and "YOUR" not in value.upper():
                    return value
    raise RuntimeError("No usable NVIDIA credential was found in the local GLM example")


def _read_existing() -> dict[str, str]:
    values: dict[str, str] = {}
    if not TARGET.exists():
        return values
    for line in TARGET.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip()] = value
    return values


def main() -> None:
    values = _read_existing()
    values.update({
        "LLM_ENABLED": "true",
        "LLM_PROVIDER": "nvidia",
        "LLM_MODEL": "z-ai/glm-5.3",
        "NVIDIA_MODEL": "z-ai/glm-5.3",
        "NVIDIA_BASE_URL": "https://integrate.api.nvidia.com/v1",
        "LLM_TEMPERATURE": "0.2",
        "LLM_TIMEOUT_SECONDS": "30",
        "LLM_MAX_RETRIES": "0",
    })
    values.setdefault("NVIDIA_API_KEY", _literal_secret())
    for name in (
        "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL",
        "GOOGLE_API_KEY", "GOOGLE_BASE_URL", "GOOGLE_MODEL",
        "KIMI_API_KEY", "KIMI_BASE_URL", "KIMI_MODEL",
    ):
        values.setdefault(name, "")
    TARGET.write_text("".join(f"{name}={value}\n" for name, value in values.items()), encoding="utf-8")
    print("Configured local variable names:", ", ".join(sorted(values)))


if __name__ == "__main__":
    main()
