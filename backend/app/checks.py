import argparse
import asyncio

from temporalio.api.workflowservice.v1 import DescribeNamespaceRequest

from app.config import get_settings
from app.db import check_database
from app.temporal.client import connect_client


async def check_temporal() -> None:
    client = await connect_client()
    await client.workflow_service.describe_namespace(
        DescribeNamespaceRequest(namespace=get_settings().temporal_namespace)
    )


async def check(target: str) -> bool:
    checks = {"database": check_database, "temporal": check_temporal}
    passed = True
    for name, operation in checks.items():
        if target not in ("all", name):
            continue
        try:
            await asyncio.wait_for(operation(), timeout=15)
            print(f"{name}: PASS")
        except Exception as error:
            # Avoid printing URLs/connection strings that may contain credentials.
            print(f"{name}: FAIL ({type(error).__name__}); check service and environment settings")
            passed = False
    return passed


def main() -> None:
    parser = argparse.ArgumentParser(description="Check real infrastructure connectivity")
    parser.add_argument("target", choices=["all", "database", "temporal"], default="all", nargs="?")
    args = parser.parse_args()
    raise SystemExit(0 if asyncio.run(check(args.target)) else 1)


if __name__ == "__main__":
    main()
