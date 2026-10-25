# data/

Not tracked by git (see `.gitignore`). Layout expected by `pipeline/paths.py` (override with the `HADITH_ROOT` environment variable):

```
data/sources/<SourceName>/     raw source datasets, see ../docs/SOURCES.md
data/HadithMaster/             build output: hadith_master.db, narrators.csv, parser/, ...
```

The finished `hadith_master.db` (4.7 GB) is distributed through Zenodo (https://doi.org/10.5281/zenodo.23630500), not through git.
Place it in `data/HadithMaster/` to use the examples and tools.
