import logging
from datetime import datetime

import numpy as np
from arrow import arrow
from pymongo import MongoClient
from sklearn.cluster import AgglomerativeClustering

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

    if station["pv-code"] == "meteoswiss":
        rating += 1

    if station["name"] != station["short"]:
        rating += 1

    return rating


def find_duplicates():
    log.info("Find duplicated stations")
    mongo_db = MongoClient("mongodb://localhost:27018/winds").get_database()

    all_stations = list(mongo_db.stations.find({"status": {"$ne": "hidden"}}))

    ids = np.array([station["_id"] for station in all_stations])

    x = [station["loc"]["coordinates"][0] for station in all_stations]
    y = [station["loc"]["coordinates"][1] for station in all_stations]
    X = np.array((x, y))
    X = X.T

    try:
        model = AgglomerativeClustering(linkage="ward", n_clusters=None, distance_threshold=0.0002)  # ~20m
        clusters = model.fit_predict(X)

        unique, count = np.unique(clusters, return_counts=True)
        duplicates = unique[count > 1]

        for cluster in duplicates:
            stations = list(
                mongo_db.stations.find(
                    {"_id": {"$in": [ids[index] for index in np.nditer(np.where(clusters == cluster))]}}
                )
            )
            now = datetime.now().timestamp()
            ratings = [station_rating(station, now) for station in stations]
            max_rating_index = np.argmax(ratings)

            logs = []
            for index, station in enumerate(stations):
                date = "N/A"
                if station.get("last", {}).get("_id"):
                    date = arrow.Arrow.fromtimestamp(station["last"]["_id"]).format("YY-MM-DD HH:mm:ssZZ")

                rating = f"{ratings[index]}*" if index == max_rating_index else ratings[index]
                left_alignment = f"{station['_id']} ({station['short']}/{station['name']})"
                logs.append(f"{rating : <3} {left_alignment : <70}{date}")

            lon = stations[0]["loc"]["coordinates"][0]
            lat = stations[0]["loc"]["coordinates"][1]
            print(f"\nhttps://winds.mobi/stations/map?lat={lat}&lon={lon}&zoom=15")
            print("\n".join(logs))
    except Exception as e:
        log.exception(f"Error while creating clusters: {e}")


if __name__ == "__main__":
    find_duplicates()
