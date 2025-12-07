from datetime import datetime

import redis
import csv

# --- Configuration ---
REDIS_HOST = "localhost"
REDIS_PORT = 6380
REDIS_DB = 0
OUTPUT_FILE = "redis_export_elevation_api.csv"
BATCH_SIZE = 10000  # Number of keys to process in a single pipeline
# ---------------------

# Initialize Redis client (decode_responses=True for clean output strings)
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)


def format_hash_value(hash_data):
    """Formats a Redis Hash dictionary into a single string for CSV."""
    if not hash_data:
        return ""

    return ",".join([f"{field}:{value}" for field, value in hash_data.items()])


def process_pipelined_results(keys, results):
    """Processes batched results (EXPIRETIME, HGETALL) and yields CSV rows."""

    # We sent 2 commands per key (EXPIRETIME, HGETALL), so results are grouped by 2.
    for i, key in enumerate(keys):
        # Result indices for the current key
        time_index = i * 2
        hash_data_index = i * 2 + 1

        time = results[time_index]
        hash_data = results[hash_data_index]  # This will be a dictionary

        # Format the time string
        time_str = datetime.fromtimestamp(time).isoformat(" ")

        # Format the value
        formatted_value = format_hash_value(hash_data)

        yield {"key": key, "value": formatted_value, "time": time_str}  # Always hash


def export_pipelined_hashes():
    """Iterates keys using SCAN and exports Hash data using Pipelining."""
    print(f"Starting optimized Hash export. Batch size: {BATCH_SIZE}")

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["key", "value", "time"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        pipeline = r.pipeline()
        current_batch_keys = []
        key_count = 0

        # Use SCAN_ITER for safe, non-blocking iteration
        for key in r.scan_iter(match="alt/*"):

            # 1. Add key to batch list
            current_batch_keys.append(key)

            # 2. Enqueue the two necessary commands for the Hash key
            pipeline.expiretime(key)  # Command 1: Get expire time
            pipeline.hgetall(key)  # Command 2: Get all fields/values of the Hash

            # 3. Execute the pipeline when the batch is full
            if len(current_batch_keys) >= BATCH_SIZE:
                results = pipeline.execute()

                # 4. Process and write results
                for row in process_pipelined_results(current_batch_keys, results):
                    writer.writerow(row)

                key_count += len(current_batch_keys)
                print(f"Exported {key_count} keys so far...")

                # Reset batch
                pipeline = r.pipeline()
                current_batch_keys = []

        # Process the last, partial batch
        if current_batch_keys:
            results = pipeline.execute()
            for row in process_pipelined_results(current_batch_keys, results):
                writer.writerow(row)
            key_count += len(current_batch_keys)

    print(f"\n✅ Optimized export complete! {key_count} keys written to **{OUTPUT_FILE}**")


if __name__ == "__main__":
    export_pipelined_hashes()
