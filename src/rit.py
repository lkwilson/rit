#!/usr/bin/env python

import sys
from rit_lib import main, RitError


if __name__ == '__main__':
  try:
    main()
  except RitError as exc:
    sys.exit(1)
