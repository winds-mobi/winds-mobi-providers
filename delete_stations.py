import argparse

import arrow
from pymongo import MongoClient

from commons.provider import get_logger
from settings import MONGODB_URL

log = get_logger('delete_stations')

parser = argparse.ArgumentParser(description='Delete stations not seen since DAYS')
parser.add_argument(
    '--days', type=int, default=60,
    help="Specify the number of days since 'last seen' before deleting the station [default: %(default)s]")
parser.add_argument('--provider', help="Delete only stations from this 'provider', for example 'jdc'")
args = vars(parser.parse_args())

mongo_db = MongoClient(MONGODB_URL).get_database()

log.info(f"Deleting stations from '{args['provider'] or 'any'}' provider not seen since {str(args['days'])} days...")

now = arrow.now().timestamp
query = {'seen': {'$lt': now - args['days'] * 3600 * 24}}
if args['provider']:
    query['pv-code'] = args['provider']
for station in mongo_db.stations.find(query):
    seen = arrow.Arrow.fromtimestamp(station['seen'])
    log.info(f"Deleting {station['_id']} ['{station['short']}'], last seen at {seen.format('YYYY-MM-DD HH:mm:ssZZ')}")
    mongo_db[station['_id']].drop()
    mongo_db.stations.remove({'_id': station['_id']})
