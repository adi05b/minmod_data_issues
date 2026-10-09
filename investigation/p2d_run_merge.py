"""Run investigation/p2_etl.yml up to and including the merge, offline.

As p2_run_etl.py, but the mineral-site service stops after writing the merged
files (mineral-sites/merged/*/*.json.lz4). It skips the TTL export and
prep_kgrel_input, which builds every merged entity in one process and does
not fit in 14 GB. The merged files hold everything prep_kgrel_input reads;
investigation/p2d_merged.py finishes the job for the entities that matter.

    CFG_FILE=upstream-p2/tests/resources/config.yml \
      .venv-p2/bin/python investigation/p2d_run_merge.py investigation/p2_etl.yml <workdir> <data repo>
"""

import sys
from pathlib import Path

from minmodkg.etl.mineral_site import MineralSiteETLService
from statickg.main import ETLPipelineRunner
from statickg.models.prelude import GitRepository

MineralSiteETLService.prep_kg_input = lambda self, args, merge_output: None
MineralSiteETLService.prep_kgrel_input = lambda self, args, merge_output: None

cfg, workdir, datadir = map(Path, sys.argv[1:4])
ETLPipelineRunner.from_config_file(cfg, workdir, GitRepository(datadir), overwrite_config=True)()
