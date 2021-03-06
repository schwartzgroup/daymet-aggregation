# About

This directory contains tools for downloading and preparing raw and aggregated
Daymet V4 data. For more information, see the
[Daymet website](https://daac.ornl.gov/cgi-bin/dataset_lister.pl?p=32)

Annual climate summary guide: https://daac.ornl.gov/DAYMET/guides/Daymet_V4_Annual_Climatology.html
Monthly climate summary guide: https://daac.ornl.gov/DAYMET/guides/Daymet_V4_Monthly_Climatology.html
Daily surface weather guide: https://daac.ornl.gov/DAYMET/guides/Daymet_Daily_V4.html

Note that **the code in this repository does not generate aggregate data for
Hawaii or Puerto Rico** because Hawaii and Puerto Rico Daymet data are in
separate raster files; as a result, geographies located in these areas will have
values of `NA`. While technically possible, work was not dedicated to amend this
because our primary air pollution models are mostly restricted to the
continental United States. However, **this code should be able to generate
aggregates for Canada**.

# Usage

Bash and R scripts have been organized into different "stages" - all scripts in
each stage are designed to be run separately before proceeding to the next
stage. Refer to the documentation at the top of each script for specific usage
instructions.

# High- vs low-memory scripts

For many scripts, there exists both high- and low-memory versions depending on
what resources are available.

The high-memory scripts are written in R and use the `data.table` library to
carry out procedures very quickly, but these scripts require that the entire
data set be loaded into memory. This may require up to ~70 GB of RAM,
especially for aggregating and generating `tmean` in stage 3.

The low-memory scripts are written in Python or Julia and take advantage of not
needing to load the entire data set to perform the necessary procedures. In
particular, the data files produced by `exactextract` are already ordered by
date and all of those files within the same geographic level also have the same
order of geographic identifiers. The Python scripts take advantage of this by
using a stack-based approach that flushes periodically once the required
information is collected.

# Requirements

System requirements:

* ~3.5 TB of space (for storing both raw Daymet data and generated data for a
  few geographies)

Command-line utilities:

* [exactextract](https://github.com/isciences/exactextract): Primary tool used
  to aggregate Daymet data
* [wget](https://www.gnu.org/software/wget/): Used to download Daymet data
* [tqdm](https://github.com/tqdm/tqdm): Python library and command-line utility
  used to display an aggregation progress bar

R packages:

* `raster` and `sf`: Used to translate shapefiles to the Daymet spatial
  reference system.
* `data.table`, `glue`, and `unglue`: Used in stages after the initial
  aggregation to do additional aggregation / joining / splitting.

Python libraries:

* `tqdm`: Used as a command-line progress bar and as a progress indicator in
  the Python scripts.
* `numpy`: For the low-memory Python scripts.

# Subdirectories

`deprecated/`: Old code and generated data, for reference. The old aggregated
data is very messy and with many extraneous rows; it is recommended to use the
new data instead, as the new data is both cleaner and smaller.

`output/`: Primary directory for generated data. This contains 3 subdirectories:

* `output/aggregated/`: Raw output of `exactextract`, in wide format, separated
  by Daymet measure and year. For small machines or unstable storage mounts, it
  is recommended to use these files as they are much smaller.

* `output/aggregated-combined/`: `exactextract` output in long format, separated
  by aggregation (max/mean/min) and Daymet measure. These combine the files from
  `output/aggregated/` into larger files that are easier to process but take up
  much more memory.

* `output/aggregated-combined-distrib/`: The contents of
  `output/aggregated-combined/` split into smaller parts for distribution on
  Harvard Dataverse.

* `output/extra/`: Extra data that are not just `exactextract` output or
  transformations of it. This subdirectory contains additional **generated**
  data, such as extreme temperature and hot/cold wave indicators.

* `output/extra-distrib/`: The contents of `output/extra`, packaged into ZIP
  archives for distribution on Harvard Dataverse.

`rawdata/`: Directory where raw Daymet data is stored.

`shapefiles/`: Directory containing shapefiles that have been transformed to the
Daymet spatial reference system. This is required for `exactextract`, which does
not have any awareness of differing spatial references on its own or the ability
to convert between spatial reference systems.

# Date transformations

Due to limitations on `exactextract` output column names, dates in the core
output files will be represented in ISO 8601 date format **without
delimiters**, i.e. YYYYMMDD. The size of the data can make parsing years,
months, and days out of this format via type conversion + substring extraction
or a date parsing library very slow; it is recommended to make use of algebra
and the `floor()` function in base R to parse out date components instead. See
below for an example:

```r
library(data.table)
data <- fread("output/aggregated-combined/zcta5_2010/mean_tmax.csv.gz")
data[, year := floor(date / 1e4)]
data[, month := floor((date / 1e4 - year) * 1e2)]
data[, day := as.integer((date / 1e2 - floor(date / 1e2)) * 1e2)]
```

In other output files, such as those in the `output/extra/` and
`output/extra-distrib/` directories, dates may be split into year, month, and
day components.
