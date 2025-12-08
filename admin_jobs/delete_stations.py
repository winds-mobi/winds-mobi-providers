import argparse
import logging

import arrow
from pymongo import MongoClient

from settings import MONGODB_URL
from winds_mobi_provider.logging import configure_logging

configure_logging()
log = logging.getLogger(__name__)


def delete_stations(days: int, provider: str | None):
    log.info(f"Deleting stations from '{provider or 'any'}' provider not seen since {days} days...")
    mongo_db = MongoClient(MONGODB_URL).get_database()

    query: dict = {
        "$or": [
            {"lastSeenAt": {"$exists": False}},
            {"lastSeenAt": {"$lt": arrow.utcnow().shift(days=-days).datetime}},
        ]
    }
    if provider:
        query["pv-code"] = provider
    nb = 0
    for station in mongo_db.stations.find(query):
        last_seen_at = arrow.get(station["lastSeenAt"]).to("local").format("YY-MM-DD HH:mm:ssZZ")
        log.info(f"Deleting {station['_id']} ['{station['short']}'], last seen at {last_seen_at}")
        mongo_db[station["_id"]].drop()
        mongo_db.stations.delete_one({"_id": station["_id"]})
        nb += 1
    log.info(f"Done, deleted {nb} stations")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delete stations not seen since DAYS")
    parser.add_argument(
        "--days", type=int, help="Specify the number of days since 'last seen' before deleting the station"
    )
    parser.add_argument(
        "--provider",
        help="Delete only stations from this 'provider', for example 'holfuy'",
    )
    args = vars(parser.parse_args())

    delete_stations(args["days"], args["provider"])
