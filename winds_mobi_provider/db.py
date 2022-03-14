from pymongo import ASCENDING, GEOSPHERE, MongoClient
import psycopg2
from datetime import datetime

from settings import MONGODB_URL, POSTGRES_URL


def db_connection():
    if POSTGRES_URL:
        return PostgresDb()
    else:
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


class PostgresDb:
    def __init__(self):
        self.conn = psycopg2.connect(POSTGRES_URL)
        self.cursor = self.conn.cursor()

    def stations_fixes(self, station_id):
        return None

    def upsert_station(self, station_id, station):
        self.cursor.execute(
            """
            INSERT INTO stations (
                id, name,
                alt,
                loc,
                peak,
                provider_code, provider_id, provider_name,
                seen,
                short,
                status,
                tz,
                url
            )
            VALUES (
                %s, %s,
                %s,
                ST_SetSRID(ST_MakePoint(%s, %s),4326),
                %s,
                %s, %s, %s,
                %s,
                %s,
                %s,
                %s,
                %s)
            ON CONFLICT ON CONSTRAINT stations_pkey
            DO NOTHING;
            """,
            (
                station_id,
                station["name"],
                station["alt"],
                station["loc"]["coordinates"][0],
                station["loc"]["coordinates"][1],
                station["peak"],
                station["pv-code"],
                station["pv-id"],
                station["pv-name"],
                datetime.fromtimestamp(station["seen"]),
                station["short"],
                station["status"],
                station["tz"],
                station["url"]["default"],
            ),
        )
        self.conn.commit()

    def has_measure(self, station_id, key):
        self.cursor.execute(
            """
            SELECT count(*) FROM measures
            WHERE station_id=%s AND ts=%s
            """,
            (station_id, datetime.fromtimestamp(key)),
        )
        cnt = self.cursor.fetchone()[0]
        return cnt > 0

    def insert_new_measures(self, station_id, station, new_measures):
        if len(new_measures) > 0:
            for measure in sorted(new_measures, key=lambda m: m["_id"]):
                pres = measure.get("pres", {"qfe": None, "qnh": None, "qff": None})
                self.cursor.execute(
                    """
                    INSERT INTO measures (
                        ts,
                        station_id,
                        wind_dir, wind_avg, wind_max,
                        temp,
                        hum,
                        pressure_qfe, pressure_qnh, pressure_qff,
                        rain,
                        updated_at
                    )
                    VALUES (
                        %s,
                        %s,
                        %s, %s, %s,
                        %s,
                        %s,
                        %s, %s, %s,
                        %s,
                        %s);
                    """,
                    (
                        datetime.fromtimestamp(measure["_id"]),
                        station_id,
                        measure.get("w-dir"),
                        measure.get("w-avg"),
                        measure.get("w-max"),
                        measure.get("temp"),
                        measure.get("hum"),
                        pres["qfe"],
                        pres["qnh"],
                        pres["qff"],
                        measure.get("rain"),
                        datetime.fromtimestamp(measure["time"]),
                    ),
                )
            self.conn.commit()
