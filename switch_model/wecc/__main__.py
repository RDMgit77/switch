# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""Script to handle switch <cmd> calls from the command line."""
from __future__ import print_function

import argparse
import sys
import switch_model.wecc.sampling.cli as sample


cmds = {
    "sample": sample.main,
}


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("subcommand", choices=cmds.keys(), help="The possible switch subcommands")

    args, remaining_args = parser.parse_known_args(args)

    # adjust the argument list to make it look like someone ran "python -m <module>" directly
    sys.argv[0] += " " + sys.argv[1]
    del sys.argv[1]

    cmds[args.subcommand]()


if __name__ == "__main__":
    main()
