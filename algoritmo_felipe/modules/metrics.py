import csv
import logging
from typing import Iterable, Dict, Any

logger = logging.getLogger(__name__)


def save_node_counts(records: Iterable[Dict[str, Any]], filepath: str) -> None:
    """Persist sampled node counts to CSV."""
    fieldnames = [
        "time",
        "total_nodes",
        "cloud_nodes",
        "proxy_nodes",
        "fog_nodes",
        "end_nodes",
        "other_nodes",
    ]
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    logger.info("Saved node count samples to %s", filepath)


def save_unprocessed_messages(simulator, filepath: str) -> None:
    """Dump in-transit and queued messages to CSV for debugging."""
    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "QueueType",
                "App",
                "Message",
                "Src",
                "Dst",
                "Timestamp",
                "Path",
                "CurrentNode",
                "Until",
            ]
        )

        # Network Queue (Messages in transit)
        if hasattr(simulator.network_ctrl_pipe, "items"):
            for msg in simulator.network_ctrl_pipe.items:
                writer.writerow(
                    [
                        "Network_Queue",
                        getattr(msg, "app_name", ""),
                        msg.name,
                        msg.src,
                        msg.dst,
                        msg.timestamp,
                        msg.path,
                        msg.dst_int,
                        "N/A",
                    ]
                )

        # Consumer Queues (Messages waiting for processing at nodes)
        for pipe_id, pipe in simulator.consumer_pipes.items():
            if hasattr(pipe, "items"):
                for msg in pipe.items:
                    writer.writerow(
                        [
                            "Processing_Queue",
                            getattr(msg, "app_name", ""),
                            msg.name,
                            msg.src,
                            msg.dst,
                            msg.timestamp,
                            msg.path,
                            msg.dst_int,
                            "N/A",
                        ]
                    )

        # Active Processing/Transit (Messages in yield)
        for entry in simulator.processing_messages:
            msg = entry.get("msg")
            if msg is None:
                continue
            writer.writerow(
                [
                    entry.get("type", ""),
                    getattr(msg, "app_name", ""),
                    msg.name,
                    msg.src,
                    msg.dst,
                    msg.timestamp,
                    msg.path,
                    msg.dst_int,
                    entry.get("until", "N/A"),
                ]
            )

    logger.info("Saved unprocessed messages snapshot to %s", filepath)
