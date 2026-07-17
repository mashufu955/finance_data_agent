"""
finance-data-agent 启动脚本
用法: .venv\\Scripts\\python.exe main.py
"""

import socket
import subprocess
import sys

import httpx


def check_docker_services():
    """检查 Docker 基础服务是否就绪"""
    services = {
        "MySQL":     ("127.0.0.1", 3306),
        "Qdrant":    ("127.0.0.1", 6333),
        "TEI Embed": ("127.0.0.1", 8081),
        "ES":        ("127.0.0.1", 9200),
    }

    all_ok = True
    for name, (host, port) in services.items():
        try:
            if name == "TEI Embed":
                r = httpx.post(f"http://{host}:{port}/",
                               json={"inputs": ["ping"]},
                               headers={"Content-Type": "application/json"},
                               timeout=5.0, trust_env=False)
                ok = r.status_code == 200
            elif name == "ES":
                r = httpx.get(f"http://{host}:{port}/_cluster/health",
                              timeout=5.0, trust_env=False)
                ok = r.status_code == 200
            elif name == "Qdrant":
                r = httpx.get(f"http://{host}:{port}/healthz",
                              timeout=5.0, trust_env=False)
                ok = r.status_code == 200
            else:
                with socket.create_connection((host, port), timeout=2):
                    ok = True
        except Exception:
            ok = False

        status = "OK" if ok else "FAIL"
        print(f"  [{status}] {name} ({host}:{port})")
        if not ok:
            all_ok = False

    return all_ok


def main():
    print("=" * 50)
    print("  Finance Data Agent - Startup")
    print("=" * 50)

    # 1. 检查 Docker 服务
    print("\n[1/2] Checking Docker services...")
    if not check_docker_services():
        print("\n  Some services are not ready.")
        print("  Please run: docker compose up -d")
        print("  Then wait for all services to start.\n")
        sys.exit(1)
    print("  All services are ready.\n")

    # 2. 启动 FastAPI 服务
    print("[2/2] Starting FastAPI server on http://127.0.0.1:8000 ...")
    print("  API docs: http://127.0.0.1:8000/docs")
    print("  Query endpoint: POST http://127.0.0.1:8000/api/query")
    print("  Press Ctrl+C to stop.\n")
    print("-" * 50)

    subprocess.run([
        sys.executable, "-m", "uvicorn",
        "app.main:app",
        "--host", "127.0.0.1",
        "--port", "8000",
    ])


if __name__ == "__main__":
    main()
