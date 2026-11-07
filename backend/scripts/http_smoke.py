"""Exercise the running read endpoints without needing database credentials."""

import json
import sys
from urllib.request import urlopen


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    for endpoint in ("stores", "orders", "order-lines", "items", "imports"):
        with urlopen(f"{base}/{endpoint}?limit=2", timeout=10) as response:
            result = json.load(response)
        assert isinstance(result["data"], list), endpoint
        assert "next_cursor" in result, endpoint
        assert result["data"], f"{endpoint}: seed fixtures before smoke testing"
        print(f"PASS GET /{endpoint}: {len(result['data'])} records")
    for endpoint in ("orders/filter", "dishes/top"):
        with urlopen(f"{base}/{endpoint}?limit=2", timeout=10) as response:
            result = json.load(response)
        assert result["data"], f"{endpoint}: seed fixtures before smoke testing"
        print(f"PASS GET /{endpoint}: {len(result['data'])} records")
    with urlopen(f"{base}/openapi.json", timeout=10) as response:
        schema = json.load(response)
    assert all(
        f"/{name}" in schema["paths"]
        for name in (
            "stores",
            "orders",
            "order-lines",
            "items",
            "imports",
            "orders/filter",
            "dishes/top",
        )
    )
    with urlopen(f"{base}/docs", timeout=10) as response:
        assert response.status == 200
    print("PASS: OpenAPI schema and interactive documentation")


if __name__ == "__main__":
    main()
