"""Print only non-secret metadata from local provider examples."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


SAFE_ID = re.compile(r"^[A-Za-z0-9._:/-]{1,160}$")


def dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{dotted(node.value)}.{node.attr}"
    return ""


def literal(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def safe_url(value: str | None) -> str | None:
    if not value or not value.startswith(("https://", "http://")):
        return None
    parsed = urlsplit(value)
    if not parsed.hostname:
        return None
    host = parsed.hostname + (f":{parsed.port}" if parsed.port else "")
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def inspect(path: Path) -> dict:
    result = {
        "file": path.name,
        "provider": path.stem.replace("-ai-api", "").replace("-api", ""),
        "base_urls": set(),
        "model_ids": set(),
        "environment_variables": set(),
        "openai_sdk_compatible": False,
        "hardcoded_secret_present": False,
        "client_calls": set(),
        "assigned_names": set(),
    }
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as error:
        result["inspection_error"] = type(error).__name__
        return result
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names]
            if (isinstance(node, ast.ImportFrom) and node.module == "openai") or "openai" in names:
                result["openai_sdk_compatible"] = True
        if isinstance(node, ast.Call):
            call_name = dotted(node.func)
            if any(marker in call_name.lower() for marker in ("client", "openai", "genai", "chat", "completion")):
                result["client_calls"].add(call_name)
            if call_name in {"os.getenv", "os.environ.get"} and node.args:
                name = literal(node.args[0])
                if name and SAFE_ID.fullmatch(name):
                    result["environment_variables"].add(name)
            for keyword in node.keywords:
                name = keyword.arg or ""
                value = literal(keyword.value)
                if name == "base_url":
                    url = safe_url(value)
                    if url:
                        result["base_urls"].add(url)
                elif name == "model" and value and SAFE_ID.fullmatch(value):
                    result["model_ids"].add(value)
                elif name in {"api_key", "token", "password"} and value:
                    result["hardcoded_secret_present"] = True
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value_node = node.value
            value = literal(value_node) if value_node is not None else None
            names = {dotted(target).lower() for target in targets}
            result["assigned_names"].update(name for name in names if name)
            if any("base_url" in name or "invoke_url" in name for name in names):
                url = safe_url(value)
                if url:
                    result["base_urls"].add(url)
            if any(name.endswith("model") or "model_id" in name for name in names):
                if value and SAFE_ID.fullmatch(value):
                    result["model_ids"].add(value)
            if any(any(marker in name for marker in ("api_key", "token", "password")) for name in names):
                if value:
                    result["hardcoded_secret_present"] = True
        if isinstance(node, ast.Dict):
            for key_node, value_node in zip(node.keys, node.values):
                key = literal(key_node) if key_node is not None else None
                value = literal(value_node)
                if key == "model" and value and SAFE_ID.fullmatch(value):
                    result["model_ids"].add(value)
                if key and key.lower() in {"authorization", "api_key", "x-api-key"}:
                    if value or isinstance(value_node, (ast.BinOp, ast.JoinedStr)):
                        result["hardcoded_secret_present"] = True
    for key in ("base_urls", "model_ids", "environment_variables", "client_calls", "assigned_names"):
        result[key] = sorted(result[key])
    return result


def main() -> None:
    root = Path(sys.argv[1]).resolve()
    for path in sorted(root.glob("*.py")):
        print(inspect(path))


if __name__ == "__main__":
    main()
