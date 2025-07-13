import re
from zoneinfo import ZoneInfo

import arrow
import requests
from lxml import html

from winds_mobi_provider import Q_, Pressure, Provider, ProviderException, StationNames, StationStatus, ureg


class PmcJoder(Provider):
    provider_code = "pmcjoder"
    provider_name = "pmcjoder.ch"
    provider_url = "https://www.pmcjoder.ch/webcam/neuhaus/wetterstation/wx.htm"

    timezone = ZoneInfo("Europe/Zurich")

    wind_directions = {
        "N": 0,
        "NNO": 1 * (360 / 16),
        "NO": 2 * (360 / 16),
        "ONO": 3 * (360 / 16),
        "O": 4 * (360 / 16),
        "OSO": 5 * (360 / 16),
        "SO": 6 * (360 / 16),
        "SSO": 7 * (360 / 16),
        "S": 8 * (360 / 16),
        "SSW": 9 * (360 / 16),
        "SW": 10 * (360 / 16),
        "WSW": 11 * (360 / 16),
        "W": 12 * (360 / 16),
        "WNW": 13 * (360 / 16),
        "NW": 14 * (360 / 16),
        "NNW": 15 * (360 / 16),
    }

    def extract_timestamp(self, data_str):
        # Use regex to extract the date and time
        match = re.search(r"Last Updated:\s*(\d{1,2}:\d{2})\s*on\s*(\d{1,2}/\d{1,2}/\d{2})", data_str)
        if match:
            time_str = match.group(1)
            date_str = match.group(2)

            # Combine date and time strings
            datetime_str = f"{date_str} {time_str}"

            # Parse the combined string using arrow
            datetime_obj = arrow.get(datetime_str, "D/M/YY H:mm").replace(tzinfo=self.timezone)

            # Convert to Unix timestamp
            return datetime_obj.int_timestamp
        else:
            raise ValueError("Date and time not found in the provided string")

    def process_data(self):
        self.log.info("Processing MyProvider data...")
        try:
            url = "https://www.pmcjoder.ch/webcam/neuhaus/wetterstation/details.htm"

            page = requests.get(url, timeout=(self.connect_timeout, self.read_timeout))

            tree = html.fromstring(page.content)

            date_blob = tree.xpath("//table//tr[3]//td[1]//font//text()")[0]

            values = tree.xpath("//table//tr[position() >= 5 and position() <= 27]//td[2]//text()")
            values = [value.strip() for value in values]

            data = [
                {
                    "id": "segelclub-neuhaus-interlaken",
                    "shortName": "Neuhuus",
                    "name": "Segelclub Neuhaus-Interlaken",
                    "latitude": 46.678212,
                    "longitude": 7.815857,
                    "altitude": 559,
                    "status": "ok",
                    "measures": [
                        {
                            "time": self.extract_timestamp(date_blob),
                            "windDirection": self.wind_directions[values[0]],
                            "windAverage": float(values[1]),
                            "windMaximum": float(values[2]),
                            "temperature": float(values[6]),
                            "pressure": float(values[7]),
                            "humidity": float(values[4]),
                        }
                    ],
                }
            ]
            for station in data:
                try:
                    winds_station = self.save_station(
                        provider_id=station["id"],
                        names=StationNames(short_name=station["shortName"], name=station["name"]),
                        latitude=station["latitude"],
                        longitude=station["longitude"],
                        altitude=station["altitude"],
                        status=StationStatus.GREEN if station["status"] == "ok" else StationStatus.RED,
                        url="https://www.pmcjoder.ch/webcam/neuhaus/wetterstation/wx.htm",
                    )

                    measure_key = station["measures"][0]["time"]
                    if not self.has_measure(winds_station, measure_key):
                        measure = self.create_measure(
                            station=winds_station,
                            _id=measure_key,
                            wind_direction=station["measures"][0]["windDirection"],
                            wind_average=Q_(station["measures"][0]["windAverage"], ureg.kilometer / ureg.hour),
                            wind_maximum=Q_(station["measures"][0]["windMaximum"], ureg.kilometer / ureg.hour),
                            temperature=Q_(station["measures"][0]["temperature"], ureg.degC),
                            pressure=Pressure(station["measures"][0]["pressure"], qnh=None, qff=None),
                            humidity=station["measures"][0]["humidity"],
                        )
                        self.insert_measures(winds_station, measure)

                except ProviderException as e:
                    self.log.warning(f"Error while processing station '{station['id']}': {e}")
                except Exception as e:
                    self.log.exception(f"Error while processing station '{station['id']}': {e}")

        except Exception as e:
            self.log.exception(f"Error while processing MyProvider: {e}")

        self.log.info("...Done !")


def pmcjoder():
    PmcJoder().process_data()


if __name__ == "__main__":
    pmcjoder()
