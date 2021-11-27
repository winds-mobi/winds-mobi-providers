from apscheduler.schedulers.blocking import BlockingScheduler
from pymongo import MongoClient

import settings
from clusters import save_clusters
from delete_stations import delete_stations
from providers.borntofly import BornToFly
from providers.ffvl import Ffvl
from providers.fluggruppe_aletsch import FluggruppeAletsch
from providers.holfuy import Holfuy
from providers.iweathar import IWeathar
from providers.metar_noaa import MetarNoaa
from providers.meteoswiss_opendata import MeteoSwiss
from providers.pdcs import Pdcs
from providers.pioupiou import Pioupiou
from providers.romma import Romma
from providers.slf import Slf
from providers.thunerwetter import ThunerWetter
from providers.windline import Windline
from providers.windspots import Windspots
from providers.yvbeach import YVBeach
from providers.zermatt import Zermatt

scheduler = BlockingScheduler()
scheduler.configure(
    executors={
        "providers": {"type": "threadpool", "max_workers": 2},
        "admin": {"type": "processpool", "max_workers": 1},
    },
    job_defaults={"misfire_grace_time": None, "coalesce": True, "max_instances": 1},
)


# Admin jobs

scheduler.add_job(
    lambda: delete_stations(MongoClient(settings.MONGODB_URL).get_database(), 60, ""),
    name="delete_stations",
    trigger="cron",
    hour="3",
    executor="admin",
)
scheduler.add_job(
    lambda: save_clusters(MongoClient(settings.MONGODB_URL).get_database(), 50),
    name="save_clusters",
    trigger="cron",
    hour="4",
    executor="admin",
)

# Providers jobs

scheduler.add_job(
    lambda: BornToFly(settings.BORN_TO_FLY_VENDOR_ID, settings.BORN_TO_FLY_DEVICE_ID).process_data(),
    name=BornToFly.provider_code,
    trigger="cron",
    minute="0-59/5",
    second=0,
    executor="providers",
)
scheduler.add_job(
    lambda: Ffvl().process_data(),
    name=Ffvl.provider_code,
    trigger="cron",
    minute="0-59/5",
    second=20,
    executor="providers",
)
scheduler.add_job(
    lambda: FluggruppeAletsch().process_data(),
    name=f"{FluggruppeAletsch.provider_code}/1",
    trigger="cron",
    minute="0-59/5",
    second=40,
    executor="providers",
)
scheduler.add_job(
    lambda: FluggruppeAletsch().process_data2(),
    name=f"{FluggruppeAletsch.provider_code}/2",
    trigger="cron",
    minute="0-59/5",
    second=50,
    executor="providers",
)
scheduler.add_job(
    lambda: Holfuy().process_data(),
    name=Holfuy.provider_code,
    trigger="cron",
    minute="1-59/5",
    second=0,
    executor="providers",
)
scheduler.add_job(
    lambda: IWeathar(settings.IWEATHAR_KEY).process_data(),
    name=IWeathar.provider_code,
    trigger="cron",
    minute="1-59/5",
    second=20,
    executor="providers",
)
scheduler.add_job(
    lambda: MetarNoaa().process_data(),
    name=MetarNoaa.provider_code,
    trigger="cron",
    minute="1-59/10",
    second=40,
    executor="providers",
)
scheduler.add_job(
    lambda: MeteoSwiss().process_data(),
    name=MeteoSwiss.provider_code,
    trigger="cron",
    minute="2-59/5",
    second=0,
    executor="providers",
)
scheduler.add_job(
    lambda: Pdcs().process_data(),
    name=Pdcs.provider_code,
    trigger="cron",
    minute="2-59/5",
    second=20,
    executor="providers",
)
scheduler.add_job(
    lambda: Pioupiou().process_data(),
    name=Pioupiou.provider_code,
    trigger="cron",
    minute="2-59/5",
    second=40,
    executor="providers",
)
scheduler.add_job(
    lambda: Romma(settings.ROMMA_KEY).process_data(),
    name=Romma.provider_code,
    trigger="cron",
    minute="3-59/5",
    second=0,
    executor="providers",
)
scheduler.add_job(
    lambda: Slf().process_data(),
    name=Slf.provider_code,
    trigger="cron",
    minute="3-59/5",
    second=20,
    executor="providers",
)
scheduler.add_job(
    lambda: ThunerWetter().process_data(),
    name=ThunerWetter.provider_code,
    trigger="cron",
    minute="3-59/5",
    second=40,
    executor="providers",
)
scheduler.add_job(
    lambda: Windline(settings.WINDLINE_SQL_URL).process_data(),
    name=Windline.provider_code,
    trigger="cron",
    minute="4-59/5",
    second=0,
    executor="providers",
)
scheduler.add_job(
    lambda: Windspots().process_data(),
    name=Windspots.provider_code,
    trigger="cron",
    minute="4-59/5",
    second=15,
    executor="providers",
)
scheduler.add_job(
    lambda: YVBeach().process_data(),
    name=YVBeach.provider_code,
    trigger="cron",
    minute="4-59/5",
    second=30,
    executor="providers",
)
scheduler.add_job(
    lambda: Zermatt(settings.ADMIN_DB_URL).process_data(),
    name=Zermatt.provider_code,
    trigger="cron",
    minute="4-59/5",
    second=45,
    executor="providers",
)


scheduler.start()
