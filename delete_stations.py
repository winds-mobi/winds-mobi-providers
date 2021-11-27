import argparse
from typing import Optional

import arrow
from pymongo import MongoClient

from settings import MONGODB_URL
from winds_mobi_provider.logging import configure_logger

log = configure_logger("delete_stations")


def delete_stations(mongo_db, days: int, provider: Optional[str]):
    log.info(f"Deleting stations from '{provider or 'any'}' provider not seen since {days} days...")

    now = arrow.now().int_timestamp
    query = {"seen": {"$lt": now - days * 3600 * 24}}
    if provider:
        query["pv-code"] = provider
    for station in mongo_db.stations.find(query):
        seen = arrow.Arrow.fromtimestamp(station["seen"])
        log.info(
            f"Deleting {station['_id']} ['{station['short']}'], last seen at {seen.format('YYYY-MM-DD HH:mm:ssZZ')}"
        )
        mongo_db[station["_id"]].drop()
        mongo_db.stations.remove({"_id": station["_id"]})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delete stations not seen since DAYS")
    parser.add_argument(
        "--days",
        type=int,
        default=60,
        help="Specify the number of days since 'last seen' before deleting the station [default: %(default)s]",
    )
    parser.add_argument(
        "--provider",
        help="Delete only stations from this 'provider', for example 'jdc'",
    )
    args = vars(parser.parse_args())

    delete_stations(MongoClient(MONGODB_URL).get_database(), args["days"], args["provider"])
