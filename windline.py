from datetime import datetime, timedelta
from urllib.parse import urlparse

import MySQLdb
import arrow
from cachetools import hashkey, cached

from commons import wgs84
from commons.provider import Provider, ProviderException, Status, ureg, Q_
from settings import WINDLINE_URL


class NoMeasure(Exception):
    pass


class Windline(Provider):
    provider_code = 'windline'
    provider_name = 'windline.ch'
    provider_url = 'http://www.windline.ch'

    # status_property_id = get_property_id('status')
    status_property_id = 13
    # altitude_property_id = get_property_id('altitude')
    altitude_property_id = 9
    # longitude_property_id = get_property_id('longitude')
    longitude_property_id = 16
    # latitude_property_id = get_property_id('latitude')
    latitude_property_id = 17

    wind_average_type = 16402
    wind_maximum_type = 16410
    wind_direction_type = 16404
    temperature_type = 16400
    humidity_type = 16401

    def __init__(self):
        super().__init__()
        self.windline_url = WINDLINE_URL

    # Windline status: offline, maintenance, demo or online
    def get_status(self, status):
        if status == 'offline':
            return Status.HIDDEN
        elif status == 'maintenance':
            return Status.RED
        elif status == 'demo':
            return Status.ORANGE
        elif status == 'online':
            return Status.GREEN
        else:
            return Status.HIDDEN

    def get_property_id(self, cursor, key):
        cursor.execute('SELECT tblstationpropertylistno FROM tblstationpropertylist WHERE uniquename=%s', (key,))
        try:
            return cursor.fetchone()[0]
        except TypeError:
            raise ProviderException(f"No property '{key}'")

    def get_property_value(self, cursor, station_no, property_id):
        cursor.execute(
            'SELECT value FROM tblstationproperty WHERE tblstationno=%s AND tblstationpropertylistno=%s',
            (station_no, property_id)
        )
        try:
            return cursor.fetchone()[0]
        except TypeError:
            raise ProviderException(f"No property value for property '{property_id}'")

    def get_measures(self, cursor, station_id, data_id, start_date):
        cursor.execute(
            'SELECT measuredate, data FROM tblstationdata '
            'WHERE stationid=%s AND dataid=%s AND measuredate>=%s '
            'ORDER BY measuredate',
            (station_id, data_id, start_date)
        )
        return cursor.fetchall()

    @cached(cache={}, key=lambda self, cursor, station_no, data_id: hashkey(station_no, data_id))
    def get_measure_correction(self, cursor, station_no, data_id):
        try:
            cursor.execute(
                'SELECT onlyvalue FROM tblcalibrate WHERE tblstationno=%s AND tbldatatypeno='
                '(SELECT tbldatatypeno FROM tbldatatype WHERE dataid=%s)',
                (station_no, data_id)
            )
            return cursor.fetchone()[0]
        except (TypeError, ValueError):
            return None

    def get_corrected_value(self, cursor, value, station_no, data_id):
        correction = self.get_measure_correction(cursor, station_no, data_id)
        if correction:
            if data_id == self.wind_direction_type:
                return (value + correction) % 360
            else:
                return value + correction
        return value

    def get_measure_value(self, rows, start_date, end_date):
        for row in reversed(rows):
            date = row[0]
            if start_date <= date <= end_date:
                return float(row[1])
        raise NoMeasure()

    def get_last_measure_value(self, rows, end_date):
        for row in reversed(rows):
            date = row[0]
            if date <= end_date:
                return float(row[1])
        raise NoMeasure()

    def process_data(self):
        try:
            self.log.info('Processing WINDLINE data...')

            connection_info = urlparse(self.windline_url)
            mysql_connection = MySQLdb.connect(connection_info.hostname, connection_info.username,
                                               connection_info.password, connection_info.path[1:], charset='utf8')

            # mysql_connection is buffered by default so we can use the same cursor with fetchall
            mysql_cursor = mysql_connection.cursor()

            start_date = datetime.utcnow() - timedelta(days=2)

            # Fetch only stations that have a status (property_id=13)
            mysql_cursor.execute(
                'SELECT tblstation.tblstationno, stationid, stationname, shortdescription, value '
                'FROM tblstation '
                'INNER JOIN tblstationproperty '
                'ON tblstation.tblstationno = tblstationproperty.tblstationno '
                'WHERE tblstationpropertylistno=%s',
                (self.status_property_id,)
            )
            for row in mysql_cursor.fetchall():
                station_no = row[0]
                windline_id = row[1]
                short_name = row[2]
                name = row[3]
                status = row[4]

                station_id = None
                try:
                    try:
                        if 6000 <= int(windline_id) < 7000:
                            # Windline integrate holfuy stations with 6xxx ids
                            raise ProviderException(f'{windline_id} is an holfuy station, discarding')
                    except ValueError:
                        pass

                    station = self.save_station(
                        windline_id,
                        short_name,
                        name,
                        wgs84.parse_dms(self.get_property_value(mysql_cursor, station_no, self.latitude_property_id)),
                        wgs84.parse_dms(self.get_property_value(mysql_cursor, station_no, self.longitude_property_id)),
                        self.get_status(status),
                        altitude=self.get_property_value(mysql_cursor, station_no, self.altitude_property_id))
                    station_id = station['_id']

                    try:
                        measures_collection = self.measures_collection(station_id)
                        new_measures = []

                        wind_average_rows = self.get_measures(
                            mysql_cursor, windline_id, self.wind_average_type, start_date)
                        wind_maximum_rows = self.get_measures(
                            mysql_cursor, windline_id, self.wind_maximum_type, start_date)
                        wind_direction_rows = self.get_measures(
                            mysql_cursor, windline_id, self.wind_direction_type, start_date)
                        temperature_rows = self.get_measures(
                            mysql_cursor, windline_id, self.temperature_type, start_date)
                        humidity_rows = self.get_measures(
                            mysql_cursor, windline_id, self.humidity_type, start_date)

                        # The wind average measure is the time reference for a measure
                        for wind_average_row in wind_average_rows:
                            try:
                                key = arrow.get(wind_average_row[0]).timestamp
                                if key not in [measure['_id'] for measure in new_measures] and \
                                        not self.has_measure(measures_collection, key):

                                    wind_average = Q_(float(wind_average_row[1]), ureg.meter / ureg.second)

                                    measure_date = wind_average_row[0]

                                    wind_maximum = Q_(float(self.get_measure_value(
                                        wind_maximum_rows,
                                        measure_date - timedelta(seconds=10),
                                        measure_date + timedelta(seconds=10))),
                                        ureg.meter / ureg.second)

                                    wind_direction = self.get_measure_value(
                                        wind_direction_rows,
                                        measure_date - timedelta(seconds=10),
                                        measure_date + timedelta(seconds=10))

                                    wind_direction = self.get_corrected_value(
                                        mysql_cursor,
                                        wind_direction,
                                        station_no,
                                        self.wind_direction_type)

                                    temperature = self.get_last_measure_value(
                                        temperature_rows,
                                        measure_date + timedelta(seconds=10))

                                    humidity = self.get_last_measure_value(
                                        humidity_rows,
                                        measure_date + timedelta(seconds=10))

                                    measure = self.create_measure(
                                        station,
                                        key,
                                        wind_direction,
                                        wind_average,
                                        wind_maximum,
                                        temperature=temperature,
                                        humidity=humidity,
                                    )
                                    new_measures.append(measure)
                            except NoMeasure:
                                pass

                        self.insert_new_measures(measures_collection, station, new_measures)

                    except ProviderException as e:
                        self.log.warn(f"Error while processing measures for station '{station_id}': {e}")
                    except Exception as e:
                        self.log.exception(f"Error while processing measures for station '{station_id}': {e}")

                except ProviderException as e:
                    self.log.warn(f"Error while processing station '{station_id}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing station '{station_id}': {e}")

        except Exception as e:
            self.log.exception(f'Error while processing Windline: {e}')
        finally:
            try:
                mysql_cursor.close()
                mysql_connection.close()
            except Exception:
                pass

        self.log.info('Done !')


Windline().process_data()
