"""Helper for start-whispertype.bat: prints the resolved venv_path from config."""
import configparser
import os
import sys

os.environ.setdefault("HOME", os.path.expanduser("~"))

ini = next(
    (p for p in ["config.ini", "config.ini.example"] if os.path.isfile(p)), None
)
if not ini:
    sys.exit(1)

c = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
c.read(ini)
v = c.get("Paths", "venv_path", fallback="")
if not v:
    sys.exit(1)

print(os.path.normpath(os.path.expandvars(os.path.expanduser(v))), end="")
