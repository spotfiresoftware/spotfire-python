# pylint: skip-file

import argparse


def output_string(value, as_string):
    if as_string:
        print(value.strip('"'))
    else:
        print(value)


def output(value, as_string, break_array):
    if break_array:
        vals = value.strip('[]').split(",")
        for v in vals:
            output_string(v.strip(), as_string)
    else:
        output_string(value, as_string)


def main():
    # Process command line arguments
    parser = argparse.ArgumentParser("Quickly parse the pyproject.toml file")
    parser.add_argument("--section", help="The section to extract from")
    parser.add_argument("--key", help="The key to extract")
    parser.add_argument("--array", action="store_true", help="Break apart arrays")
    parser.add_argument("--string", action="store_true", help="Print strings unquoted")
    args = parser.parse_args()

    # Now parse the file
    with open("pyproject.toml", "r") as f:
        for line in f.readlines():
            if line.startswith('['):
                in_section = line.strip().strip('[]')
            else:
                split = line.split('=', 1)
                key = split[0].strip()
                value = split[1].strip()
                if in_section == args.section and key == args.key:
                    output(value, args.string, args.array)


if __name__ == "__main__":
    main()
