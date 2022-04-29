#!/usr/bin/env python3
#
# Convert files of tmin and tmean and their corresponding quantiles generated by
# stage3_extreme_weather.R into a file of hot and cold waves and singleton
# extreme weather events, where waves are defined as two or more days of
# extreme weather concurrently and a singleton extreme weather event is a day
# of extreme weather not followed or preceded  by another day of extreme
# weather.
#
# The output file will have a unique ID for each wave or singleton extreme
# weather event, the length of the wave or "1" for singleton events, and the
# index of the day in the wave e.g. "1" for the 1st day, "2" for the 2nd day,
# etc.
#
# Contact: Edgar Castro <edgar_castro@g.harvard.edu>

import collections
import csv
import datetime
import gzip
import os
import typing

import tqdm

DEFAULT_TMAX_FILENAME = "mean_tmax.csv.gz"
DEFAULT_TMIN_FILENAME = "mean_tmin.csv.gz"
DEFAULT_TMAX_QUANTILES_FILENAME = "tmax_quantiles.csv.gz"
DEFAULT_TMIN_QUANTILES_FILENAME = "tmin_quantiles.csv.gz"
DEFAULT_OUTPUT_FILENAME_TEMPLATE = "extreme_temps_pctile{:02d}_pctile{:02d}.csv.gz"
DEFAULT_CUTOFF_QUANTILES = [
    (1, 99),
    (3, 97),
    (5, 95),
    (10, 90),
    (15, 85)
]


class ExtremeWaveDetector:

    def __init__(self,
                 id_field: str,
                 extreme_label: str,  # "hot" or "cold"
                 output_fp: typing.TextIO,
                 wave_id_start: int = 0):
        """ Initialize ExtremeWaveDetector class.

        Args:
            id_field: The field containing geographic identifiers.
            extreme_label: Either "hot" or "cold".
            output_fp: An output file pointer where CSV data will be written to.
            wave_id_start: The ID of the first wave. If continuing from a
                previous ExtremeWaveDetector class, this should be the wave_id
                of the last wave.
        """

        self.id_field = id_field
        self.extreme_label = extreme_label

        self.last_date = datetime.datetime(1, 1, 1)
        self.last_id = None

        self.date_stack = []

        self.wave_id = wave_id_start

        self.csv_writer = csv.DictWriter(
            output_fp,
            fieldnames=[self.id_field] + [
                "year", "month", "day", "extreme", "wave_id", "wave_index",
                "wave_length"
            ]
        )
        if wave_id_start == 0:
            self.csv_writer.writeheader()

    def dump_stack(self) -> None:
        """ Dump the stack.

        Dumps all dates in the current stack to the output_fp set in the class
        instantiation step.
        """

        self.wave_id += 1
        for (i, date) in enumerate(self.date_stack):
            result = {
                self.id_field: self.last_id,
                "year": date.year,
                "month": date.month,
                "day": date.day,
                "extreme": self.extreme_label,
                "wave_id": self.wave_id,
                "wave_index": i + 1,
                "wave_length": len(self.date_stack)
            }
            self.csv_writer.writerow(result)
        self.date_stack = []

    def push(self, line) -> None:
        """ Push a line to the stack.

        Args:
            line: A row of data created by stage2_combine.R.
        """

        new_id = line[self.id_field]
        new_date = datetime.datetime(
            int(line["date"][:4]),
            int(line["date"][4:6]),
            int(line["date"][6:8])
        )

        # If the ID changes or there is a gap of more than a day, dump the
        # stack
        if (
                (new_id != self.last_id)
                or ((new_date - self.last_date).days > 1)
        ):
            if len(self.date_stack) > 0:
                self.dump_stack()
            self.date_stack = []

        # Grow the stack
        self.date_stack.append(new_date)

        self.last_date = new_date
        self.last_id = new_id


def detect_id_column(path: str) -> str:
    """ Detect the GEOID column for a given file.

    Args:
        path: The path to a CSV file created by stage2_combine.R.

    Returns: The first fieldname of the given path.
    """

    with gzip.open(path, "rt") as input_fp:
        return next(csv.reader(input_fp))[0]


# Return format: result[year][id]
def extract_quantiles(input_path: str,
                      quantile: int) -> dict[str, dict[float]]:
    """ Extract quantiles from a file created by stage3_temp_quantiles.R.

    Args:
        input_path: The path to a file created by stage3_temp_quantiles.R
        quantile: The quantile to extract. e.g. 1st percentile -> 1

    Returns: A nested dict where the first index is the year and the second
    index is the GEOID.
    """

    result = collections.defaultdict(dict)
    quantile_field = "pctile{:02d}".format(quantile)
    with gzip.open(input_path, "rt") as input_fp:
        reader = csv.DictReader(input_fp)
        id_field = reader.fieldnames[0]
        for line in tqdm.tqdm(reader, desc="Reading {}".format(input_path)):
            result[line["year"]][line[id_field]] = float(line[quantile_field])
    return result


def extract_extremes(tmax_path: str,
                     cold_cutoffs_tmax: dict[str, dict[str, float]],
                     tmin_path: str,
                     hot_cutoffs_tmin: dict[str, dict[str, float]],
                     output_path: str
                     ) -> None:
    """ Extract extreme temperature days and waves.

    Example:

        extract_extremes(
            tmax_path="data/aggregated-combined/counties_2010/mean_tmax.csv.gz",
            cold_cutoffs_tmax=extract_quantiles("data/extra/counties_2010/tmax_quantiles.csv.gz", 1),
            tmin_path="data/aggregated-combined/mean_tmin.csv.gz",
            hot_cutoffs_tmin=extract_quantiles("data/extra/counties_2010/tmin_quantiles.csv.gz", 99),
            output_path="data/extra/counties_2010/extreme_temps.csv.gz.csv.gz"
        )

    Args:
        tmax_path: The path to a mean_tmax.csv.gz created by stage2_combine.R.
        cold_cutoffs_tmax: The upper bound of tmax for a day to be considered
            an extreme cold day, generated by the extract_quantiles function.
        tmin_path: The path to a mean_tmin.csv.gz created by stage2_combine.R.
        hot_cutoffs_tmin: The lower bound of tmin for a day to be considered
            an extreme heat day, generated by the extract_quantiles function.
        output_path: The path that extreme temperatures should be written to.
    """

    temp_path = output_path + ".temp"

    with gzip.open(temp_path, "wt") as output_fp:
        last_wave_id = None

        # Detect cold waves
        with gzip.open(tmax_path, "rt") as input_fp:
            reader = csv.DictReader(input_fp)
            id_field = reader.fieldnames[0]

            cold_days = [
                line
                for line in tqdm.tqdm(reader, desc="> Extracting extreme cold days")
                if float(line["value"]) < cold_cutoffs_tmax[line["date"][:4]].get(line[id_field], -1e100)
            ]

            tqdm.tqdm.write("> Sorting extreme cold days")
            cold_days = sorted(
                cold_days,
                key=lambda line: (line[id_field], line["date"])
            )

            wave_detector = ExtremeWaveDetector(
                id_field=id_field,
                extreme_label="cold",
                output_fp=output_fp,
            )
            for line in tqdm.tqdm(cold_days, desc="> Detecting cold waves"):
                wave_detector.push(line)

            # Dump last stack
            wave_detector.dump_stack()

            # Save last wave ID for the heat wave detector
            last_wave_id = wave_detector.wave_id

        # Detect heat waves
        with gzip.open(tmin_path, "rt") as input_fp:
            reader = csv.DictReader(input_fp)
            id_field = reader.fieldnames[0]

            hot_days = [
                line
                for line in tqdm.tqdm(reader, desc="> Extracting extreme heat days")
                if float(line["value"]) > hot_cutoffs_tmin[line["date"][:4]].get(line[id_field], -1e100)
            ]

            tqdm.tqdm.write("> Sorting extreme heat days")
            hot_days = sorted(
                hot_days,
                key=lambda line: (line[id_field], line["date"])
            )

            wave_detector = ExtremeWaveDetector(
                id_field=id_field,
                extreme_label="hot",
                output_fp=output_fp,
                wave_id_start=last_wave_id
            )
            for line in tqdm.tqdm(hot_days, desc="> Detecting cold waves"):
                wave_detector.push(line)

            # Dump last stack
            wave_detector.dump_stack()

    os.rename(temp_path, output_path)


if __name__ == "__main__":
    import argparse
    import glob

    parser = argparse.ArgumentParser()
    parser.add_argument("-T", "--tmax", default=None)
    parser.add_argument("-M", "--tmax-quantiles", default=None)
    parser.add_argument("-C", "--tmax-cutoff-quantile", default=1, type=int)
    parser.add_argument("-t", "--tmin", default=None)
    parser.add_argument("-m", "--tmin-quantiles", default=None)
    parser.add_argument("-c", "--tmin-cutoff-quantile", default=99, type=int)
    parser.add_argument("-o", "--output", default=None)
    parser.add_argument("-a", "--autofill-args", default=None)
    args = parser.parse_args()

    # Input given: convert the given file
    if all([
        args.tmax, args.tmax_quantiles, args.tmax_cutoff_quantile,
        args.tmax, args.tmax_quantiles, args.tmin_cutoff_quantile,
        args.output
    ]):
        extract_extremes(
            tmax_path=args.tmax,
            cold_cutoffs_tmax=extract_quantiles(args.tmax_quantiles, args.tmax_cutoff_quantile),
            tmin_path=args.tmin,
            hot_cutoffs_tmin=extract_quantiles(args.tmin_quantiles, args.tmin_cutoff_quantile),
            output_path=args.output
        )

    # No input given: determine what files need to be converted by looking for
    # missing files in the expected daymet-aggregation output directory
    # hierarchy
    else:
        # If args.auto is given: use that as the only extra_directories
        if args.autofill_args:
            extra_directories = [args.autofill_args]
        else:
            extra_directories = glob.glob("output/extra/*")
        for extra_directory in extra_directories:
            tmax_path = os.path.join(
                extra_directory.replace("extra", "aggregated-combined"),
                DEFAULT_TMAX_FILENAME
            )
            tmin_path = os.path.join(
                extra_directory.replace("extra", "aggregated-combined"),
                DEFAULT_TMIN_FILENAME
            )
            cold_cutoffs_tmax = os.path.join(extra_directory, DEFAULT_TMAX_QUANTILES_FILENAME)
            hot_cutoffs_tmin = os.path.join(extra_directory, DEFAULT_TMIN_QUANTILES_FILENAME)

            for path in [
                tmax_path,
                tmin_path,
                cold_cutoffs_tmax,
                hot_cutoffs_tmin
            ]:
                if not os.path.isfile(path):
                    raise Exception("ERROR: {} does not exist".format(path))

            for tmax_cutoff_quantile, tmin_cutoff_quantile in DEFAULT_CUTOFF_QUANTILES:
                output_path = os.path.join(
                    extra_directory,
                    DEFAULT_OUTPUT_FILENAME_TEMPLATE.format(
                        tmax_cutoff_quantile,
                        tmin_cutoff_quantile
                    )
                )
                if os.path.isfile(output_path):
                    print("Skipping {}".format(extra_directory))
                else:
                    print("Generating {}".format(output_path))
                    extract_extremes(
                        tmax_path=tmax_path,
                        cold_cutoffs_tmax=extract_quantiles(cold_cutoffs_tmax, tmax_cutoff_quantile),
                        tmin_path=tmin_path,
                        hot_cutoffs_tmin=extract_quantiles(hot_cutoffs_tmin, tmin_cutoff_quantile),
                        output_path=output_path
                    )
