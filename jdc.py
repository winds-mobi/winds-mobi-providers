import base64
import email
import email.policy
import imaplib
import json
import os
import subprocess
import urllib
import urllib.parse
from os import path

import psycopg2
from psycopg2.extras import RealDictCursor

from commons.provider import Provider, ProviderException, Status, Pressure, ureg, Q_
from settings import (JDC_IMAP_SERVER, JDC_IMAP_USERNAME, JDC_IMAP_PASSWORD, JDC_DELETE_EMAILS, JDC_ADMIN_DB_URL,
                      JDC_PHP_PATH)

current_dir = path.dirname(os.path.abspath(__file__))


class Jdc(Provider):
    provider_code = 'jdc'
    provider_name = 'jdc.ch'
    provider_url = 'http://meteo.jdc.ch'

    speed_units = {
        'm/s': ureg.meter / ureg.second,
        'km/h': ureg.kilometer / ureg.hour,
    }

    def __init__(self, imap_server, imap_username, imap_password, delete_emails, admin_db_url, php_path='php'):
        super().__init__()

        self.imap_server = imap_server
        self.imap_username = imap_username
        self.imap_password = imap_password
        self.delete_emails = delete_emails
        self.admin_db_url = admin_db_url
        self.php_path = php_path

    def m2a_to_json(self, data: bytes):
        proc = subprocess.Popen([self.php_path, 'm2a_to_json.php'], cwd=path.join(current_dir, 'jdc'),
                                stdout=subprocess.PIPE, stdin=subprocess.PIPE)
        proc.stdin.write(base64.b64encode(data))
        proc.stdin.close()
        result = proc.stdout.read()
        proc.wait()
        return json.loads(result)

    def get_status(self, status):
        if status == 'unactive':
            return Status.HIDDEN
        elif status == 'active':
            return Status.GREEN
        elif status == 'maintenance':
            return Status.RED
        elif status == 'test':
            return Status.ORANGE
        elif status == 'waiting':
            return Status.RED
        elif status == 'wintering':
            return Status.RED
        elif status == 'moved':
            return Status.ORANGE
        else:
            return Status.HIDDEN

    def get_stations_metadata(self):
        connection = None
        cursor = None
        try:
            connection = psycopg2.connect(self.admin_db_url)
            cursor = connection.cursor(cursor_factory=RealDictCursor)
            cursor.execute('select * from winds_mobi_jdc_station')
            return cursor.fetchall()
        finally:
            try:
                cursor.close()
                connection.close()
            except Exception:
                pass

    def find_value(self, measure, typ):
        values = list(filter(lambda m: m['type'] == typ, measure['mesures']))
        if len(values) > 1:
            self.log.warning(f"Multiple values found for '{typ}'")

        if len(values) > 0:
            value = values[-1]['valeur']
            unit = values[-1]['unit']
            if unit in self.speed_units:
                return Q_(value, self.speed_units[unit])
            else:
                return value
        else:
            return None

    def save_measures(self, jdc_id, blocs, stations_metadata):
        try:
            jdc_station = list(filter(lambda d: str(d['id']) == jdc_id, stations_metadata))[0]
            station = self.save_station(
                jdc_id,
                jdc_station['short_name'],
                jdc_station['name'],
                jdc_station['latitude'],
                jdc_station['longitude'],
                self.get_status(jdc_station['status']),
                altitude=jdc_station['altitude'],
                url=urllib.parse.urljoin(self.provider_url, '/station/' + jdc_id)
            )
            station_id = station['_id']

            try:
                jdc_measures = blocs[0]['mesures']
            except Exception:
                self.log.warning('Unable to find a bloc with measures')
                jdc_measures = []

            self.log.info(f"Station '{jdc_id}' ({station['name']}) found {len(jdc_measures)} measures")

            measures_collection = self.measures_collection(station_id)
            for jdc_measure in jdc_measures:
                key = jdc_measure['datetime']
                if not self.has_measure(measures_collection, key):
                    try:
                        new_measure = self.create_measure(
                            station,
                            key,
                            self.find_value(jdc_measure, 'Direction du vent'),
                            self.find_value(jdc_measure, 'Vent moyen'),
                            self.find_value(jdc_measure, 'Vent max'),
                            temperature=self.find_value(jdc_measure, "Température de l'air"),
                            humidity=self.find_value(jdc_measure, 'Humidité'),
                            pressure=Pressure(
                                qfe=self.find_value(jdc_measure, 'Pression atmosphérique'),
                                qnh=None,
                                qff=None),
                            rain=self.find_value(jdc_measure, 'Pluviométrie')
                        )
                        self.insert_new_measures(measures_collection, station, [new_measure])
                    except ProviderException as e:
                        self.log.warning(
                            f"Error while processing measure '{key}' for station '{station_id}': {e}")
                    except Exception as e:
                        self.log.exception(
                            f"Error while processing measure '{key}' for station '{station_id}': {e}")

        except ProviderException as e:
            self.log.warning(f"Error while processing station '{jdc_id}': {e}")

        except Exception as e:
            self.log.exception(f"Error while processing station '{jdc_id}': {e}")

    def process_data(self):
        try:
            self.log.info('Processing JDC data...')

            stations_metadata = self.get_stations_metadata()

            mail = imaplib.IMAP4_SSL(self.imap_server)
            mail.login(self.imap_username, self.imap_password)
            try:
                typ, data = mail.select()
                nb_msg = int(data[0])
                self.log.info(f'There are {nb_msg} messages in the inbox')

                for i in range(1, nb_msg + 1):
                    try:
                        typ, data = mail.fetch(str(i), '(RFC822)')
                        message = email.message_from_bytes(data[0][1], policy=email.policy.default)
                        jdc_payload = message.get_payload(1)
                        jdc_filename = jdc_payload.get_filename()
                        jdc_content = jdc_payload.get_payload(decode=True)
                        try:
                            jdc_station = self.m2a_to_json(jdc_content)
                            jdc_id = jdc_station['infos']['serial']
                            self.save_measures(jdc_id, jdc_station['blocs'], stations_metadata)
                        except Exception:
                            self.log.exception(f"Unable to parse attachment '{jdc_filename}'")
                        finally:
                            typ, data = mail.store(str(i), '+FLAGS', r'\Deleted')
                            if not typ == 'OK':
                                self.log.error(f"Unable to delete email '{message['subject']}'")
                    except Exception:
                        self.log.exception(f'Unable to load email #{i}')
            finally:
                if self.delete_emails:
                    mail.expunge()
                mail.logout()

        except Exception as e:
            self.log.exception(f'Error while processing JDC: {e}')

        self.log.info('Done !')


Jdc(JDC_IMAP_SERVER, JDC_IMAP_USERNAME, JDC_IMAP_PASSWORD, JDC_DELETE_EMAILS, JDC_ADMIN_DB_URL, JDC_PHP_PATH
    ).process_data()
