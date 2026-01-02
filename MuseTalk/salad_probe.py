import json
import os
import platform
import shutil
import subprocess
import sys
from typing import Any, Dict, List

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None  # type: ignore


def run(cmd: List[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Command {' '.join(cmd)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def collect_gpu_info() -> List[Dict[str, Any]]:
    gpus: List[Dict[str, Any]] = []
    try:
        out = run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,driver_version,compute_cap",
                "--format=csv,noheader,nounits",
            ]
        )
    except Exception as e:
        return [{"error": str(e)}]

    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        idx, name, mem_total, driver, compute_cap = parts[:5]
        try:
            mem_total_mib = int(mem_total)
        except ValueError:
            mem_total_mib = None  # type: ignore
        gpus.append(
            {
                "index": int(idx),
                "name": name,
                "memory_total_mib": mem_total_mib,
                "driver_version": driver,
                "compute_capability": compute_cap,
            }
        )
    return gpus


def collect_cpu_info() -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "logical_cores": os.cpu_count(),
    }
    model = None
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/cpuinfo", "r", encoding="utf-8") as f:
                for line in f:
                    if "model name" in line:
                        model = line.split(":", 1)[1].strip()
                        break
        except Exception:
            model = None
    info["model"] = model

    if psutil is not None:
        try:
            freq = psutil.cpu_freq()
            if freq is not None:
                info["frequency_mhz"] = freq.max or freq.current
        except Exception:
            pass

    return info


def collect_ram_info() -> Dict[str, Any]:
    if psutil is None:
        return {}
    try:
        vm = psutil.virtual_memory()
        return {
            "total_bytes": vm.total,
            "total_gib": vm.total / (1024 ** 3),
        }
    except Exception:
        return {}


def collect_disk_info(path: str = "/") -> Dict[str, Any]:
    try:
        usage = shutil.disk_usage(path)
        return {
            "path": path,
            "total_bytes": usage.total,
            "total_gib": usage.total / (1024 ** 3),
            "free_bytes": usage.free,
            "free_gib": usage.free / (1024 ** 3),
        }
    except Exception as e:
        return {"path": path, "error": str(e)}


def main() -> None:
    node_id = os.environ.get("SALAD_NODE_ID") or os.environ.get("HOSTNAME")

    payload: Dict[str, Any] = {
        "node_id": node_id,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
        },
        "gpu": collect_gpu_info(),
        "cpu": collect_cpu_info(),
        "ram": collect_ram_info(),
        "disk_root": collect_disk_info("/"),
    }

    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

