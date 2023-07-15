import argparse
import logging
from datetime import datetime

import numpy as np
from pymongo import MongoClient, UpdateMany, UpdateOne
from scipy.spatial import KDTree
from sklearn.cluster import AgglomerativeClustering

from settings import MONGODB_URL
from winds_mobi_provider.logging import configure_logging

configure_logging()
log = logging.getLogger(__name__)


def save_clusters(nb_clusters):
    log.info(f"Creating {nb_clusters} station's clusters")
    mongo_db = MongoClient(MONGODB_URL).get_database()

    now = datetime.now().timestamp()
    all_stations = list(
        mongo_db.stations.find({"status": {"$ne": "hidden"}, "last._id": {"$gt": now - 30 * 24 * 3600}})
    )
    range_clusters = np.geomspace(20, len(all_stations), num=nb_clusters, dtype=int)

    ids = np.array([station["_id"] for station in all_stations])

    x = [station["loc"]["coordinates"][0] for station in all_stations]
    y = [station["loc"]["coordinates"][1] for station in all_stations]
    X = np.array((x, y))
    X = X.T

    try:
        bulk_operations = [UpdateMany({}, {"$set": {"clusters": []}})]
        for n_clusters in reversed(range_clusters):

            model = AgglomerativeClustering(linkage="ward", connectivity=None, n_clusters=n_clusters)
            labels = model.fit_predict(X)

            for label in range(len(np.unique(labels))):
                cluster_assign = labels == label
                cluster = X[cluster_assign]

                average = np.average(cluster, 0)
                middle = cluster[KDTree(cluster).query(average)[1]]

                indexes = np.where((X == middle).all(axis=1))[0]
                if len(indexes) > 1:
                    stations = list(
                        mongo_db.stations.find(
                            {"_id": {"$in": [ids[index] for index in indexes.tolist()]}}, {"last._id": 1}
                        )
                    )
                    values = {station["_id"]: station.get("last", {}).get("_id", 0) for station in stations}
                    station_id = max(values.keys(), key=(lambda k: values[k]))
                    if values[station_id] != 0:
                        log.warning(f"Multiple 'middle' found, '{station_id}' has the latest measure")
                    else:
                        log.warning(f"Ignoring '{ids[cluster_assign]}', stations have no measures")
                        continue
                    index = np.where(ids == station_id)[0][0]
                else:
                    index = indexes[0]
                log.info(f"{n_clusters}: {ids[cluster_assign]} -> {ids[index]}")
                bulk_operations.append(UpdateOne({"_id": ids[index]}, {"$addToSet": {"clusters": int(n_clusters)}}))

        mongo_db.stations.bulk_write(bulk_operations)
        log.info(f"Done, created {nb_clusters} clusters")
    except Exception as e:
        log.exception(f"Error while creating clusters: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Save station's clusters in mongodb")
    parser.add_argument(
        "--num", type=int, default=50, help="Specify the number of cluster levels [default: %(default)s]"
    )
    args = vars(parser.parse_args())

    save_clusters(args["num"])
