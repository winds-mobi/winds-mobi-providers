from pymongo import ASCENDING, GEOSPHERE, MongoClient

from settings import MONGODB_URL


def db_connection():
    if MONGODB_URL:
        return MongoDb()


class MongoDb:

    def __init__(self):
        self.mongo_db = MongoClient(MONGODB_URL).get_database()
        self.__stations_collection = self.mongo_db.stations
        self.__stations_collection.create_index(
            [
                ("loc", GEOSPHERE),
                ("status", ASCENDING),
                ("pv-code", ASCENDING),
                ("short", ASCENDING),
                ("name", ASCENDING),
            ]
        )
        self.collection_names = self.mongo_db.collection_names()

    def stations_collection(self):
        return self.__stations_collection

    def measures_collection(self, station_id):
        if station_id not in self.collection_names:
            self.mongo_db.create_collection(station_id, **{"capped": True, "size": 500000, "max": 5000})
            self.collection_names.append(station_id)
        return self.mongo_db[station_id]

    def stations_fixes(self, station_id):
        return self.mongo_db.stations_fix.find_one(station_id)

    def upsert_station(self, station_id, station):
        self.stations_collection().update({"_id": station_id}, {"$set": station}, upsert=True)

    def has_measure(self, station_id, key):
        measure_collection = self.measures_collection(station_id)
        return measure_collection.find({"_id": key}).count() > 0

    def __add_last_measure(self, measure_collection, station_id):
        last_measure = measure_collection.find_one({"$query": {}, "$orderby": {"_id": -1}})
        if last_measure:
            self.stations_collection().update({"_id": station_id}, {"$set": {"last": last_measure}})

    def insert_new_measures(self, station_id, station, new_measures):
        if len(new_measures) > 0:
            measure_collection = self.measures_collection(station_id)
            measure_collection.insert(sorted(new_measures, key=lambda m: m["_id"]))
            self.__add_last_measure(measure_collection, station["_id"])
