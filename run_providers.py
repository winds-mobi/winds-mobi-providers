from datetime import datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler


def run_providers():
    scheduler = BlockingScheduler()
    scheduler.configure(
        executors={
            "admin": {"type": "processpool", "max_workers": 1},
            "providers": {"type": "processpool", "max_workers": 2},
        },
        job_defaults={
            "misfire_grace_time": 3 * 60,
            "coalesce": True,  # Reschedule a single job if it failed 3 minutes ago
            "max_instances": 1,  # Only 1 job instance executing concurrently
        },
    )

    # Admin jobs
    scheduler.add_job(
        "admin_stations:delete_stations",
        args=(60, ""),
        trigger="cron",
        hour="3",
        executor="admin",
    )
    scheduler.add_job(
        "admin_clusters:save_clusters",
        args=(50,),
        trigger="cron",
        hour="4",
        executor="admin",
    )

    # start_date must be in the future when the scheduler starts
    start_date = datetime.now().astimezone() + timedelta(seconds=10)

    for provider_job in [
        # Alphabetical order
        ("providers.borntofly:borntofly", 5),
        ("providers.ffvl:ffvl", 5),
        ("providers.fluggruppe_aletsch:fluggruppe_aletsch", 5),
        ("providers.holfuy:holfuy", 5),
        ("providers.iweathar:iweathar", 5),
        ("providers.metar_noaa:metar_noaa", 10),
        ("providers.meteoswiss_opendata:meteoswiss", 5),
        ("providers.pdcs:pdcs", 5),
        ("providers.pioupiou:pioupiou", 5),
        ("providers.romma:romma", 5),
        ("providers.slf:slf", 5),
        ("providers.thunerwetter:thunerwetter", 5),
        ("providers.windline:windline", 5),
        ("providers.windspots:windspots", 5),
        ("providers.windy:windy", 5),
        ("providers.yvbeach:yvbeach", 5),
        ("providers.zermatt:zermatt", 5),
    ]:
        func = provider_job[0]
        interval = provider_job[1]
        scheduler.add_job(
            func,
            trigger="interval",
            start_date=start_date,
            minutes=interval,
            jitter=5 * 60,  # randomize start_date during 5 minutes period
            executor="providers",
        )
    scheduler.start()


if __name__ == "__main__":
    run_providers()
