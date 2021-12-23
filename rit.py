#!/usr/bin/env python

import logging
import sys
import argparse


logger = logging.getLogger(__name__)


''' API '''

def init():
  logger.debug("init")

def commit(*, msg: str):
  logger.debug('commit')
  logger.debug('  msg: %s', msg)

def checkout(*, ref: str, force: bool):
  logger.debug('checkout')
  logger.debug('  ref: %s', ref)
  logger.debug('  force: %s', force)

def branch(*, name: str, ref: str, force: bool):
  logger.debug('branch')
  logger.debug('  name: %s', name)
  logger.debug('  ref: %s', ref)
  logger.debug('  force: %s', force)

def tag(*, name: str, ref: str, force: bool):
  logger.debug('tag')
  logger.debug('  name: %s', name)
  logger.debug('  ref: %s', ref)
  logger.debug('  force: %s', force)

def log(*, ref: str, all: bool, oneline: bool):
  logger.debug('log')
  logger.debug('  ref: %s', ref)
  logger.debug('  all: %s', all)
  logger.debug('  oneline: %s', oneline)


''' ARG HANDLERS '''

def init_main(argv, prog):
  parser = argparse.ArgumentParser(description="Initialize a raw backup directory", prog=prog)
  args = parser.parse_args(argv)
  return init(**vars(args))

def commit_main(argv, prog):
  parser = argparse.ArgumentParser(description="Create a commit from the current state", prog=prog)
  parser.add_argument('msg', help="The commit msg")
  args = parser.parse_args(argv)
  return commit(**vars(args))

def checkout_main(argv, prog):
  parser = argparse.ArgumentParser(description="Log the current commit history", prog=prog)
  parser.add_argument('ref', help="The ref to checkout")
  parser.add_argument('-f', '--force', action='store_true', help="If there are uncommitted changes, automatically remove them.")
  args = parser.parse_args(argv)
  return checkout(**vars(args))

def branch_main(argv, prog):
  parser = argparse.ArgumentParser(description="Create a new branch", prog=prog)
  parser.add_argument('name', help="The name of the branch")
  # TODO: change this to optional positional
  parser.add_argument('-r', '--ref', default='HEAD', help="The head of the new branch. By default, HEAD.")
  parser.add_argument('-f', '--force', action='store_true', help="The head of the new branch. By default, HEAD.")
  args = parser.parse_args(argv)
  return branch(**vars(args))

def tag_main(argv, prog):
  parser = argparse.ArgumentParser(description="Create a new tag", prog=prog)
  parser.add_argument('name', help="The name of the tag")
  parser.add_argument('-r', '--ref', default='HEAD', help="The head of the new tag. By default, HEAD.")
  parser.add_argument('-f', '--force', action='store_true', help="The head of the new tag. By default, HEAD.")
  args = parser.parse_args(argv)
  return tag(**vars(args))

def log_main(argv, prog):
  parser = argparse.ArgumentParser(description="Log the current commit history", prog=prog)
  parser.add_argument('-r', '--ref', default='HEAD', help="The head of the branch to log. By default, HEAD.")
  parser.add_argument('--all', action='store_true', help="Include all branches")
  parser.add_argument('--oneline', action='store_true', help="Show commits with a single line")
  args = parser.parse_args(argv)
  return log(**vars(args))

command_handlers = dict(
  init = init_main,
  commit = commit_main,
  checkout = checkout_main,
  branch = branch_main,
  tag = tag_main,
  log = log_main,
)

def setup_logger(verbose: int):
  black, red, green, yellow, blue, magenta, cyan, white = range(8)
  reset_seq = "\033[0m"
  color_seq = "\033[1;{}m"

  color_section = color_seq + "{}" + reset_seq

  if verbose == 0:
    level = logging.WARNING
  elif verbose == 1:
    level = logging.INFO
  else:
    level = logging.DEBUG

  format = "%(levelname)s: %(message)s"

  logging.basicConfig(level=level, format=format)

  logging.addLevelName(logging.DEBUG, color_section.format(30 + magenta, logging.getLevelName(logging.DEBUG)[0]))
  logging.addLevelName(logging.INFO, color_section.format(30 + blue, logging.getLevelName(logging.INFO)[0]))
  logging.addLevelName(logging.WARNING, color_section.format(30 + yellow, logging.getLevelName(logging.WARNING)[0]))
  logging.addLevelName(logging.ERROR, color_section.format(30 + red, logging.getLevelName(logging.ERROR)[0]))

def main(argv):
  parser = argparse.ArgumentParser(description="A raw version control system", add_help=False)
  parser.add_argument('command', choices=command_handlers.keys())
  parser.add_argument('--verbose', '-v', action='count', default=0)
  args, sub_argv = parser.parse_known_args(argv)
  logger.debug("Parsed args: %s", args)
  logger.debug("Extra args: %s", sub_argv)
  setup_logger(args.verbose)
  return command_handlers[args.command](sub_argv, prog=f'{parser.prog} {args.command}')

if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))
