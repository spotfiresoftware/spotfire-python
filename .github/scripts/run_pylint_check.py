import argparse
import io
import sys

from ghapi.all import GhApi
import pylint.lint
from pylint.__pkginfo__ import __version__ as pl_version


def run_pylint(directory):
    saved_stdout = sys.stdout
    sys.stdout = io.StringIO()
    result = pylint.lint.Run([directory], exit=False)
    output = sys.stdout.getvalue()
    saved_stdout.write(output)
    sys.stdout.close()
    sys.stdout = saved_stdout
    return output, result.linter.msg_status


def main():
    # Process command line arguments
    parser = argparse.ArgumentParser(
        "Check if any opened issues have been closed, run pylint, and open an issue if pylint complains")
    parser.add_argument("--repo", help="The owner and repository we are operating on")
    parser.add_argument("--label", help="The name of the GitHub label for generated issues")
    parser.add_argument("--src", help="The source directory to run pylint on")
    args = parser.parse_args()
    # Connect to GitHub REST API
    api = GhApi()
    # Determine if we should run pylint
    open_issues = api.search.issues_and_pull_requests(f"repo:{args.repo} label:{args.label} is:issue is:open")
    if open_issues.total_count != 0:
        print(f"Skipping pylint run due to existing issue {open_issues['items'][0]['html_url']}.")
        sys.exit(0)
    # Now run pylint
    (output, pylint_exitcode) = run_pylint(args.src)
    if pylint_exitcode == 0:
        sys.exit(0)
    # File an issue
    issue_body = (f"A version of `pylint` is available in the Python package repositories that identifies issues "
                  f"with the `spotfire` package.  Since we attempt to keep all pylint issues out of the source "
                  f"code (either by fixing the issue identified or by disabling that message with a localized "
                  f"comment), this is indicative of a new check in this new version of `pylint`.\n\n"
                  f"Please investigate these issues, and either fix the source or disable the check with a "
                  f"comment.  Further checks by this automation will be held until this issue is closed.  Make "
                  f"sure that the fix updates the `pylint` requirement in `requirements_dev.txt` to the version "
                  f"identified here ({pl_version}).\n\n"
                  f"For reference, here is the output of this version of `pylint`:\n\n"
                  f"```\n"
                  f"$ pylint {args.src}\n"
                  f"{output}\n"
                  f"```\n\n"
                  f"*This issue was automatically opened by the `pylint.yaml` workflow.*\n")
    owner_repo = args.repo.split("/")
    new_issue = api.issues.create(owner=owner_repo[0], repo=owner_repo[1],
                                  title=f"New version of pylint ({pl_version}) identifies new issues",
                                  body=issue_body, labels=[args.label])
    print(f"Opened issue {new_issue['html_url']}")


if __name__ == "__main__":
    main()
