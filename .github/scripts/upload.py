# pylint: skip-file

import argparse
import io
import os
import tempfile
import urllib.request as rq
import zipfile

import twine.repository
from github import Github
from twine import repository, package


def raw_download(requester, url):
    status, headers, data = requester.requestBlob("GET", url)
    if status == 302:
        req = rq.Request(headers["location"])
        with rq.urlopen(req) as resp:
            status = resp.status
            headers = dict(resp.headers.items())
            data = resp.read()
    return status, headers, data


def main():
    # Process command line arguments
    parser = argparse.ArgumentParser("Perform release activities and upload artifacts to the right endpoints.")
    parser.add_argument("--release", metavar="VERSION", help="The version number to release")
    parser.add_argument("--pypi-token", metavar="TOKEN", help="The PyPI API token to use")
    parser.add_argument("--gh-token", metavar="TOKEN", help="The GitHub API token to use")
    parser.add_argument("--repo", help="The owner and repository we are operating on")
    parser.add_argument("--relnotes", metavar="FILE", help="File containing the text of the notes for the "
                                                           "GitHub release")
    args = parser.parse_args()

    # Read the release notes
    with open(args.relnotes, "r") as relnotes_file:
        relnotes_text = relnotes_file.read()

    # Connect to GitHub REST API
    gh = Github(args.gh_token)
    repo = gh.get_repo(args.repo)

    # Download artifacts from current release branch build workflow
    with tempfile.TemporaryDirectory() as tempdir:
        branch = f"release/{args.release}"
        print(f"Searching for workflow runs for '{branch}' branch")
        workflow_run = repo.get_workflow_runs(branch=branch)[0]
        print(f"Found run {workflow_run.id}")
        for a in workflow_run.get_artifacts():
            if a.name == "sdist" or a.name.startswith("wheel-"):
                print(f"Downloading artifact '{a.name}' from {a.archive_download_url}")
                _, _, a_data = raw_download(repo._requester, a.archive_download_url)
                with zipfile.ZipFile(io.BytesIO(a_data)) as a_zip:
                    for a_zip_entry in a_zip.namelist():
                        print(f"Extracting {a_zip_entry}")
                        a_zip.extract(a_zip_entry, tempdir)

        # Create a new release
        print(f"Creating GH release")
        gh_release = repo.create_git_release(tag=f"v{args.release}", name=args.release, target_commitish=branch,
                                             message=relnotes_text, draft=False, prerelease=False)

        # Upload artifacts to GH release
        for filename in os.scandir(tempdir):
            print(f"Uploading {filename.path} to GH release")
            gh_release.upload_asset(filename.path)

        # Upload artifacts to PyPI
        pypi_url = "https://upload.pypi.org/legacy/"
        print(f"Uploading to PyPI at {pypi_url}")
        pypi_repo = twine.repository.Repository(pypi_url, "__token__", args.pypi_token, disable_progress_bar=True)
        pypi_pkgs = []
        for filename in os.scandir(tempdir):
            pypi_pkg = twine.package.PackageFile.from_filename(filename.path, None)
            pypi_pkgs.append(pypi_pkg)
            pypi_response = pypi_repo.upload(pypi_pkg)
            if pypi_response.text:
                print(f"Message from PyPI: {pypi_response.text}")
        pypi_release = pypi_repo.release_urls(pypi_pkgs)
        if pypi_release:
            print(f"Release available on PyPI at {pypi_release}")


if __name__ == "__main__":
    main()
