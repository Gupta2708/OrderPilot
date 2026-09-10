import argparse
import asyncio
import logging

from temporalio.worker import Worker

from app.config import get_settings
from app.temporal.activities import ALL_ACTIVITIES
from app.temporal.client import connect_client
from app.temporal.workflow import OrderSupervisorWorkflow


async def run_worker(smoke: bool = False) -> None:
    client = await connect_client()
    worker = Worker(
        client,
        task_queue=get_settings().temporal_task_queue,
        workflows=[OrderSupervisorWorkflow],
        activities=ALL_ACTIVITIES,
    )
    async with worker:
        logging.info(
            "OrderPilot worker started; workflow and %s activities registered",
            len(ALL_ACTIVITIES) + 1,
        )
        if smoke:
            await asyncio.sleep(2)
        else:
            await asyncio.Event().wait()


def main() -> None:
    parser = argparse.ArgumentParser(description="OrderPilot Temporal worker")
    parser.add_argument("--smoke", action="store_true", help="Start the worker, then shut down")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(run_worker(smoke=args.smoke))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
