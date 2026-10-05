"""Run investigation/p2_etl.yml once, offline.

statickg's CLI calls `git pull` on the data repo before running; this calls the
same runner without that, so the data stays pinned at its checked-out commit.

    CFG_FILE=upstream-p2/tests/resources/config.yml \
      .venv-p2/bin/python investigation/p2_run_etl.py investigation/p2_etl.yml kgdata-p2 data-p2
"""

import sys
from pathlib import Path

from statickg.main import ETLPipelineRunner
from statickg.models.prelude import GitRepository

cfg, workdir, datadir = map(Path, sys.argv[1:4])
ETLPipelineRunner.from_config_file(cfg, workdir, GitRepository(datadir), overwrite_config=True)()
