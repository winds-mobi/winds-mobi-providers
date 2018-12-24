import argparse

from commons.uwxutils import TWxUtils

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--alt', type=int, help='Altitude')
    parser.add_argument('--qnh', type=float, help='QNH')
    parser.add_argument('--qfe', type=float, help='QFE')
    args = parser.parse_args()

    if args.alt is None:
        raise Exception('Altitude not provided')

    if args.qfe is None:
        qfe = TWxUtils.AltimeterToStationPressure(args.qnh, elevationM=args.alt)
        print(f'qfe={qfe}')

    if args.qnh is None:
        qnh = TWxUtils.StationToAltimeter(args.qfe, elevationM=args.alt, algorithm='aaMADIS')
        print(f'qnh={qnh}')
