# arc

Analysis, reporting and certification for the Ravenscar Seed Testing Station.

The station tests seed lots for merchants and issues the certificates that
travel with the seed. This is the software that runs it: booking lots in,
recording what the bench found, deciding whether the figures may be reported,
issuing certificates, and keeping the sample afterwards in case somebody
disputes one.

There is no web front end and there is not going to be one. Four analysts share
one room, the worksheets are on paper, and what they need is something that
answers a question in one line without leaving the terminal they already have
open.

## Running it

```
pip install -e ".[dev]"
arc station
```

Every command takes `--database` and defaults to `var/arc.sqlite3`. The
database migrates itself when it is opened, because the station has no
operations team and the first person in on Monday should not have to know that
a release needed a schema step.

## A job, start to finish

```
arc lot book-in L-2025-0041 --species wheat --weight 24000 \
    --containers bag --container-count 480 --merchant "Ravenscar Grain" \
    --sealed-on 2025-03-04 --origin GB

arc purity record L-2025-0041 --working 120.0 --pure 118.2 \
    --other 0.9 --inert 0.9 --analyst "J. Whitfield"

arc germination record L-2025-0041 \
    --tray 96,4,0,0,0 --tray 95,5,0,0,0 --tray 97,3,0,0,0 --tray 96,4,0,0,0 \
    --set-down 2025-03-12 --final-count 2025-03-20 --analyst "J. Whitfield"

arc certificate issue L-2025-0041 --signed-by "A. Pearce"
arc certificate print GB-0214/2025/00001
```

The station records what was counted and works the percentages out itself. A
command that took a germination percentage would let somebody certify their own
arithmetic.

## What it will not let you do

Most of the value is in the refusals, and they are not warnings. A command that
is refused exits non zero and writes nothing.

- A germination whose four trays disagree too widely is not a germination, it
  is a test that has to be set down again.
- A dormant sample cannot be reported as a poor one. Treat it, repeat it, and
  the certificate says which treatment was used.
- A purity analysis that lost more than 5 per cent of the working sample
  between the balance and the piles is void.
- A complete search that found no other seed cannot go on a certificate whose
  purity analysis weighed some.
- A thousand seed weight whose eight replicates scattered too far stops the
  certificate rather than quietly not appearing on it.
- A lot already booked in cannot be booked in again, so a merchant re-sending
  last week's list does not reset seed that is halfway through testing.

## Where things are

| what | where |
| --- | --- |
| The handbook numbers, per species | `src/arc/species/table.py` |
| Sampling intensity and reduction | `src/arc/sampling/` |
| Purity, germination, moisture, seed weight | `src/arc/purity/`, `src/arc/germination/`, `src/arc/moisture/`, `src/arc/weight/` |
| Other species counted by number | `src/arc/otherseed/` |
| Tolerances between two results | `src/arc/purity/tolerance.py`, `src/arc/germination/tolerance.py`, `src/arc/otherseed/tolerance.py` |
| Between laboratories | `src/arc/referee/` |
| Certificates and what may go on one | `src/arc/certificates/` |
| The retained sample and its period | `src/arc/retention/` |
| Storage and migrations | `src/arc/storage/` |
| The command line | `src/arc/cli/` |
| Registers, statistics and the printed form | `src/arc/reporting/` |

## Checks

```
python -m pytest
python -m ruff check . && python -m ruff format --check .
python -m mypy
python -m arc.tools.check_migrations
```

`arc doctor` is the other one, and it is about the database rather than the
code: certificates with no sample behind them, jars recorded as holding less
than nothing, lots that have been in test for two months, disputes nobody
answered. It exits non zero on anything serious, so it can be a Monday morning
job that nobody reads unless it complains.

## Keeping the sample

The station keeps what is left of every submitted sample after the certificate
goes out, because a certificate is a claim somebody may dispute a year later
and the only way to answer is to test the same sample again.

```
arc store show L-2025-0041
arc store due
arc backup --to /mnt/share/backups
```

`arc backup` goes through SQLite's backup API rather than copying the file,
which would give a database from halfway through somebody's certificate, and it
opens the copy afterwards to check it is one.
