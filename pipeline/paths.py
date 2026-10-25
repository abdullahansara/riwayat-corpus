"""Central path configuration. Set HADITH_ROOT to a folder laid out as:

    <HADITH_ROOT>/sources/<SourceName>/...   raw source datasets (see docs/SOURCES.md)
    <HADITH_ROOT>/HadithMaster/              build output (hadith_master.db, narrators.csv, ...)

Default HADITH_ROOT is ../data relative to this repository.
"""
import os
PIPE = os.path.dirname(os.path.abspath(__file__)).replace('\\', '/') + '/'
ROOT = os.environ.get('HADITH_ROOT', os.path.join(PIPE, '..', 'data')).replace('\\', '/').rstrip('/') + '/'
SRC = ROOT + 'sources/'
OUT = ROOT + 'HadithMaster/'
HERE = PIPE          # helper modules and label files live next to the scripts
os.makedirs(OUT, exist_ok=True)
