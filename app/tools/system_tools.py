import ast
import ctypes
import operator
import os
import platform
import shutil
import subprocess
from typing import Dict, Any

# Safe math operators
OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

MAX_ABS_VALUE = 10 ** 12
MAX_EXPONENT = 1000


def _check_number(value):
    if isinstance(value, bool):
        raise TypeError("Booleanos não são permitidos em cálculos.")
    if isinstance(value, complex):
        raise TypeError("Números complexos não são suportados.")
    if abs(value) > MAX_ABS_VALUE:
        raise ValueError(f"Valor acima do limite permitido ({MAX_ABS_VALUE}).")
    return value


def _eval_expr(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return _check_number(node.value)
        raise TypeError(f"Tipo não suportado: {type(node.value)}")
    elif isinstance(node, ast.BinOp):
        left = _eval_expr(node.left)
        right = _eval_expr(node.right)
        op_type = type(node.op)
        if op_type not in OPERATORS:
            raise TypeError(f"Operador não suportado: {op_type}")
        if op_type is ast.Pow:
            if not isinstance(right, (int, float)) or abs(right) > MAX_EXPONENT:
                raise ValueError(f"Expoente limitado a {MAX_EXPONENT}.")
        result = OPERATORS[op_type](left, right)
        return _check_number(result)
    elif isinstance(node, ast.UnaryOp):
        operand = _eval_expr(node.operand)
        op_type = type(node.op)
        if op_type in OPERATORS:
            return _check_number(OPERATORS[op_type](operand))
        raise TypeError(f"Operador unário não suportado: {op_type}")
    else:
        raise TypeError(f"Expressão inválida: {type(node)}")


def calculate(expression: str) -> Dict[str, Any]:
    """Safely evaluates mathematical expressions without eval()."""
    if not isinstance(expression, str) or len(expression) > 500:
        return {"expression": expression, "error": "Expressão inválida ou longa demais.", "status": "error"}
    try:
        parsed = ast.parse(expression.strip(), mode="eval")
        result = _eval_expr(parsed.body)
        return {"expression": expression, "result": result, "status": "success"}
    except Exception as e:
        return {"expression": expression, "error": str(e), "status": "error"}


def get_system_info() -> Dict[str, Any]:
    """Retrieves basic system state."""
    total, used, free = shutil.disk_usage("C:\\")
    return {
        "os": platform.system(),
        "os_version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "disk_c": {
            "total_gb": round(total / (1024**3), 2),
            "free_gb": round(free / (1024**3), 2),
            "used_gb": round(used / (1024**3), 2)
        }
    }


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def get_system_metrics() -> Dict[str, Any]:
    """
    Retorna métricas em tempo real de hardware: RAM, VRAM/GPU, CPU e Disco.
    Útil para o assistente monitorar o estado do computador sem instalar ferramentas externas.
    """
    metrics: Dict[str, Any] = {
        "cpu": {
            "processor": platform.processor(),
            "architecture": platform.machine(),
            "logical_cores": os.cpu_count() or 1,
        },
        "ram": {},
        "gpu": {},
        "disk_c": {},
    }

    # 1. RAM via Windows API
    try:
        stat = _MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            total_gb = round(stat.ullTotalPhys / (1024**3), 2)
            free_gb = round(stat.ullAvailPhys / (1024**3), 2)
            used_gb = round(total_gb - free_gb, 2)
            metrics["ram"] = {
                "total_gb": total_gb,
                "used_gb": used_gb,
                "free_gb": free_gb,
                "usage_percent": stat.dwMemoryLoad,
            }
    except Exception as e:
        metrics["ram"] = {"error": str(e)}

    # 2. GPU via nvidia-smi (se presente)
    try:
        res = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,memory.free,temperature.gpu,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if res.returncode == 0 and res.stdout.strip():
            parts = [p.strip() for p in res.stdout.strip().split(",")]
            if len(parts) >= 6:
                metrics["gpu"] = {
                    "name": parts[0],
                    "total_vram_mb": int(parts[1]),
                    "used_vram_mb": int(parts[2]),
                    "free_vram_mb": int(parts[3]),
                    "temperature_c": int(parts[4]),
                    "utilization_percent": int(parts[5]),
                }
    except Exception:
        metrics["gpu"] = {"status": "Nenhuma GPU NVIDIA detectada ou nvidia-smi indisponível"}

    # 3. Disco C:
    try:
        total, used, free = shutil.disk_usage("C:\\")
        metrics["disk_c"] = {
            "total_gb": round(total / (1024**3), 2),
            "used_gb": round(used / (1024**3), 2),
            "free_gb": round(free / (1024**3), 2),
            "usage_percent": round((used / total) * 100, 1) if total else 0,
        }
    except Exception as e:
        metrics["disk_c"] = {"error": str(e)}

    return metrics
