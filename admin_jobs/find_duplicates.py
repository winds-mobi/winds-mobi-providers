import argparse
import logging
from datetime import datetime

import numpy as np
from arrow import Arrow
from pymongo import MongoClient, UpdateMany, UpdateOne
from sklearn.cluster import AgglomerativeClustering

from settings import MONGODB_URL
from winds_mobi_provider import StationStatus
from winds_mobi_provider.logging import configure_logging

configure_logging()
log = logging.getLogger(__name__)


def station_rating(station, now):
    rating = 0

    status = station["status"]
    if status == StationStatus.GREEN:
        rating += 20
    elif status == StationStatus.ORANGE:
        return 5
    elif status == StationStatus.RED:
        return 1

    last_measure = station.get("last", {}).get("_id")
    if last_measure:
        if last_measure > now - 30 * 60:
            rating += 25
        elif last_measure > now - 3600:
            rating += 20
        elif last_measure > now - 5 * 24 * 3600:
            rating += 5
        rating += 2

    if station["pv-code"] in ["meteoswiss", "pioupiou"]:
        rating += 1

    if station["name"] != station["short"]:
        rating += 1

    return rating


def find_duplicates(distance):
    log.info(f"Find duplicate stations within a given distance of {distance} meters")
    mongo_db = MongoClient(MONGODB_URL).get_database()

    all_stations = list(mongo_db.stations.find({"status": {"$ne": "hidden"}}))

    ids = np.array([station["_id"] for station in all_stations])

    x = [station["loc"]["coordinates"][0] for station in all_stations]
    y = [station["loc"]["coordinates"][1] for station in all_stations]
    X = np.array((x, y))
    X = X.T

    try:
        bulk_operations: list[UpdateMany | UpdateOne] = [UpdateMany({}, {"$set": {"duplicates": None}})]
        model = AgglomerativeClustering(linkage="ward", n_clusters=None, distance_threshold=distance / 100000)
        clusters = model.fit_predict(X)

        unique, count = np.unique(clusters, return_counts=True)
        duplicates = unique[count > 1]

        now = datetime.now().timestamp()
        num_duplicates_stations = 0
        for cluster in duplicates:
            stations = list(
                mongo_db.stations.find(
                    {"_id": {"$in": [ids[index] for index in np.nditer(np.where(clusters == cluster))]}}
                )
            )
            ratings = [station_rating(station, now) for station in stations]
            highest_rating_index = np.argmax(ratings)
            num_duplicates_stations += len(stations)

            logs = []
            for index, station in enumerate(stations):
                bulk_operations.append(
                    UpdateOne(
                        {"_id": station["_id"]},
                        {
                            "$set": {
                                "duplicates": {
                                    "stations": [station["_id"] for station in stations],
                                    "rating": ratings[index],
                                    "is_highest_rating": bool(index == highest_rating_index),
                                }
                            }
                        },
                    )
                )

                date = "N/A"
                if station.get("last", {}).get("_id"):
                    date = Arrow.fromtimestamp(station["last"]["_id"]).format("YY-MM-DD HH:mm:ssZZ")
                rating = f"{ratings[index]}*" if index == highest_rating_index else ratings[index]
                left_alignment = f"{station['_id']} ({station['short']}/{station['name']})"
                logs.append(f"{rating: <3} {left_alignment: <70}{date}")

            lon = stations[0]["loc"]["coordinates"][0]
            lat = stations[0]["loc"]["coordinates"][1]
            log.info(f"https://winds.mobi/stations/map?lat={lat}&lon={lon}&zoom=15")
            for log_line in logs:
                log.info(log_line)

        mongo_db.stations.bulk_write(bulk_operations)
        log.info(f"Found {num_duplicates_stations} station in {len(duplicates)} clusters")
    except Exception as e:
        log.exception(f"Error finding duplicate stations: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Find duplicate stations within a given distance")
    parser.add_argument("--distance", type=int, help="Maximum distance in meters between 2 duplicate stations")
    args = vars(parser.parse_args())
    find_duplicates(args["distance"])
