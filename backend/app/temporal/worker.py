import argparse
import asyncio
import logging

from temporalio import activity
from temporalio.worker import Worker

from app.config import get_settings
from app.temporal.client import connect_client


@activity.defn
async def scaffold_health() -> str:
    """Infrastructure probe only; no order or business behavior."""
    return "ok"


async def run_worker(smoke: bool = False) -> None:
    client = await connect_client()
    worker = Worker(
        client, task_queue=get_settings().temporal_task_queue, activities=[scaffold_health]
    )
    async with worker:
        logging.info("Stage 0 activity worker started; no order workflow is registered")
        if smoke:
            await asyncio.sleep(2)
        else:
            await asyncio.Event().wait()


def main() -> None:
    parser = argparse.ArgumentParser(description="OrderPilot Stage 0 activity worker")
    parser.add_argument("--smoke", action="store_true", help="Start the worker, then shut down")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(run_worker(smoke=args.smoke))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
