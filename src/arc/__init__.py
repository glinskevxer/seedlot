"""Analysis, reporting and certification for a seed testing laboratory.

The station tests seed lots on behalf of merchants and growers and issues
certificates that travel with the seed. Almost everything in here exists
because a rule in the testing handbook says a result is only valid when it was
arrived at a particular way, and because somebody has to be able to prove that
two years later.
"""

__all__ = ["__version__", "STATION_CODE", "STATION_NAME"]

__version__ = "1.0.0"

#: The accreditation code printed on every certificate the station issues.
STATION_CODE = "GB-0214"

#: The legal name of the station, likewise printed on every certificate.
STATION_NAME = "Ravenscar Seed Testing Station"
