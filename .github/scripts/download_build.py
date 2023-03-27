# pylint: skip-file

import argparse
import io
import logging
import os
import sys
import zipfile

from ghapi.all import GhApi
from ghapi.page import paged


def find_workflows(api, owner, repo, path):
    for wf in api.actions.list_repo_workflows(owner, repo).workflows:
        logging.debug("workflow id %d, %s ('%s')", wf.id, wf.path, wf.name)
        if wf.path == path:
            logging.debug("That's the one!")
            return wf.id
    logging.error("Build workflow for file '%s' not found", path)
    sys.exit(2)


def find_runs(api, owner, repo, workflow_id, build_number):
    for result in paged(api.actions.list_workflow_runs, owner, repo, workflow_id):
        for run in result.workflow_runs:
            logging.debug("run id %d #%d", run.id, run.run_number)
            if run.run_number == build_number:
                logging.debug("That's the one!")
                return run.id
    logging.error("Build workflow run not found")
    sys.exit(3)


def main():
    logging.basicConfig(level=os.environ.get('LOGLEVEL', 'WARNING').upper())
    # Process command line arguments
    parser = argparse.ArgumentParser(description="Download all artifacts attached to a build.")
    parser.add_argument("--build", type=int, required=True, help="Build number to download")
    parser.add_argument("--dir", required=True, help="Directory to download artifacts to")
    args = parser.parse_args()
    # Connect to GitHub REST API
    api = GhApi()
    owner = "TIBCOSoftware"
    repo = "spotfire-python"
    # List workflows
    workflow_id = find_workflows(api, owner, repo, '.github/workflows/build.yaml')
    # Find the id for our run
    run_id = find_runs(api, owner, repo, workflow_id, args.build)
    # Now grab each artifact
    result = api.actions.list_workflow_run_artifacts(owner, repo, run_id)
    for artifact in result.artifacts:
        logging.debug("artifact %d %s (%d bytes)", artifact.id, artifact.name, artifact.size_in_bytes)
        download = api.actions.download_artifact(owner, repo, artifact.id, 'zip')
        with zipfile.ZipFile(io.BytesIO(download)) as z:
            z.extractall(args.dir)
        logging.debug("artifact downloaded")


if __name__ == '__main__':
    main()
