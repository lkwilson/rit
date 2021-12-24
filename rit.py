#!/usr/bin/env python

import json
import time
import argparse
import hashlib
import logging
import os
import sys
from dataclasses import asdict, dataclass
from typing import Optional, Tuple


logger = logging.getLogger(__name__)
rit_dir_name = '.rit'
default_branch_name = 'main'
head_ref_name = 'HEAD'


''' fs util '''

def mkdir(*args, exists_ok=False, **kwargs):
  try:
    os.mkdir(*args, **kwargs)
  except FileExistsError:
    if not exists_ok:
      raise

''' FS STRUCTS '''

@dataclass
class RitPaths:
  root: str
  ''' The directory to backup is stored here '''

  rit_dir: str
  ''' All rit information is stored here '''

  branches: str
  '''
  References are stored here. The filename is the ref name or head_ref_name.
  head_ref_name lets us know what branch or commit the current working directory
  is.
  '''

  commits: str
  ''' Commit info is stored here. The filename is commit_id. '''

  backups: str
  ''' Backups are stored here, full and partial.  '''

  work: str
  ''' A place to temporarily store files '''

  @staticmethod
  def build_rit_paths(root: str, init: bool = False):
    root = os.path.realpath(root)
    rit_dir = os.path.join(root, rit_dir_name)
    if init:
      os.makedirs(rit_dir)
    branches = os.path.join(rit_dir, 'branches')
    mkdir(branches, exists_ok=True)
    commits = os.path.join(rit_dir, 'commits')
    mkdir(commits, exists_ok=True)
    backups = os.path.join(rit_dir, 'backups')
    mkdir(backups, exists_ok=True)
    work = os.path.join(rit_dir, 'work')
    mkdir(work, exists_ok=True)
    return RitPaths(
      root = root,
      rit_dir = rit_dir,
      branches = branches,
      commits = commits,
      backups = backups,
      work = work,
    )


''' STRUCTS '''

@dataclass
class Commit:
  parent_commit_id: Optional[str]
  commit_id: str
  create_time: float
  msg: str

@dataclass
class Branch:
  name: str
  commit_id: str

@dataclass
class HeadNode:
  commit_id: Optional[str]
  branch_name: Optional[str]

  def __post_init__(self):
    assert (self.commit_id is None) != (self.branch_name is None), "HEAD must be a branch name or a commit id"

class RitError(Exception):
  def __init__(self, msg, *args):
    super(RitError, self).__init__()
    self.msg = msg
    self.args = args

def require(statement, msg, *args):
  if not statement:
    raise RitError(msg, *args)

''' MANAGERS '''

def get_paths():
  cwd = os.path.realpath(os.getcwd())
  rit_dir = os.path.join(cwd, rit_dir_name)
  last_cwd = None
  while not os.path.isdir(rit_dir):
    last_cwd = cwd
    cwd = os.path.dirname(cwd)
    require(last_cwd != cwd, "Unable to locate rit directory")
    rit_dir = os.path.join(cwd, rit_dir_name)
  return RitPaths.build_rit_paths(cwd)

def read_head(paths: RitPaths):
  try:
    with open(os.path.join(paths.rit_dir, head_ref_name)) as fin:
      return HeadNode(**json.loads(fin))
  except FileNotFoundError:
    return HeadNode(None, default_branch_name)

def write_head(paths: RitPaths, head: HeadNode):
  with open(os.path.join(paths.rit_dir, head_ref_name), 'w') as fout:
    json.dump(asdict(head), fout)

def get_tar_path(paths: RitPaths, commit_id: str):
  return os.path.join(paths.backups, commit_id + '.tar')

def get_snar_path(paths: RitPaths, commit_id: str):
  return os.path.join(paths.backups, commit_id + '.snar')

def get_head_commit_id(paths: RitPaths, head: HeadNode = None):
  if head is None:
    head = read_head(paths)
  if head.commit_id is not None:
    return head.commit_id
  else:
    try:
      return read_branch(paths, head.branch_name).commit_id
    except FileNotFoundError:
      return None

def hash_commit(create_time: float, msg: str, snar: str, tar: str):
  logger.debug("Calculating the hash of ref")
  ref_hash = hashlib.sha1()

  ref_hash.update(b'create_time')
  ref_hash.update(str(create_time).encode('utf-8'))

  ref_hash.update(b'msg')
  ref_hash.update(msg.encode('utf-8'))

  ref_hash.update(b'snar')
  with open(snar, 'rb') as fin:
    ref_hash.update(fin.read())

  ref_hash.update(b'tar')
  with open(tar, 'rb') as fin:
    ref_hash.update(fin.read())

  return ref_hash.hexdigest()

def read_commit(paths: RitPaths, commit_id: str):
  with open(os.path.join(paths.commits, commit_id)) as fin:
    return Commit(dict(**json.load(fin), commit_id=commit_id))

def write_commit(paths: RitPaths, commit: Commit):
  logger.debug("Creating commit entry: %s", commit.commit_id)
  with open(os.path.join(paths.commits, commit.commit_id), 'w') as fout:
    data = asdict(commit)
    del data['commit_id']
    json.dump(data, fout)

def write_branch(paths: RitPaths, branch_name: str, commit_id: str):
  logger.debug("Moving branch %s to %s", branch_name, commit_id)
  branch = Branch(branch_name, commit_id)
  if is_commit(paths, branch_name):
    raise RitError('Not creating a reference with the same name as a commit id')
  data = asdict(branch)
  del data['name']
  with open(os.path.join(paths.branches, branch_name), 'w') as fout:
    json.dump(data, fout)

def read_branch(paths: RitPaths, name: str):
  with open(os.path.join(paths.branches, name)) as fin:
    return Branch(dict(**json.load(fin), name=name))

def is_branch(paths: RitPaths, name: str):
  try:
    read_branch(paths, name)
    return True
  except FileNotFoundError:
    return False

def is_commit(paths: RitPaths, commit_id: str):
  try:
    read_commit(paths, commit_id)
    return True
  except FileNotFoundError:
    return False

def resolve_ref(paths: RitPaths, ref_name_or_commit_id: str) -> Optional[Tuple[Commit, bool]]:
  try:
    return read_commit(paths, ref_name_or_commit_id), False
  except FileNotFoundError:
    pass
  try:
    ref = read_branch(paths, ref_name_or_commit_id)
  except FileNotFoundError:
    return None
  try:
    return read_commit(ref.commit_id), True
  except FileNotFoundError:
    pass
  raise RitError("Found a reference, but couldn't locate the commit!")

def create_commit(paths: RitPaths, create_time: float, msg: str):
  head = read_head(paths)
  parent_commit_id = get_head_commit_id(paths)
  logger.debug("Parent ref: %s", parent_commit_id)

  work_tar = os.path.join(paths.work, 'ref.tar')
  logger.debug("Creating tar: %s", work_tar)

  work_snar = os.path.join(paths.work, 'ref.snar')
  logger.debug("Creating snar: %s", work_snar)

  tar_cmd = ['tar', '-cg', work_snar, '-f', work_tar, paths.root, f'--exclude={rit_dir_name}']
  logger.debug("Tar command: %s", tar_cmd)

  if parent_commit_id is not None:
    head_snar = get_snar_path(paths, parent_commit_id)
    logger.debug("Copying previous snar: %s", head_snar)
    with open(head_snar, 'rb') as fin:
      with open(work_snar, 'wb') as fout:
        # TODO: This probably doesn't work with large files, and there might
        # be a better way to copy
        fout.write(fin.read())
  else:
    logger.debug("Using fresh snar file since no parent commit")

  logger.debug("Creating ref backup and snar")
  # TODO: call tar instead
  with open(work_snar, 'w') as fout:
    fout.write(f"This is a snar test {create_time}\n")
  with open(work_tar, 'w') as fout:
    fout.write(f"This is a tar test {create_time}\n")

  commit_id = hash_commit(create_time, msg, work_snar, work_tar)

  logger.debug("Moving working snar into backups directory")
  snar = get_snar_path(paths, commit_id)
  os.rename(work_snar, snar)

  logger.debug("Moving working tar into backups directory")
  tar = get_tar_path(paths, commit_id)
  os.rename(work_tar, tar)

  commit = Commit(parent_commit_id, commit_id, create_time, msg)
  write_commit(paths, commit)

  update_head(paths, commit_id, head)

def update_head(paths, commit_id, head = None):
  if head is None:
    head = read_head(paths)
  if head.commit_id is not None:
    head.commit_id = commit_id
    write_head(paths, head)
  else:
    write_branch(paths, head.branch_name, commit_id)

''' API '''

def init():
  logger.debug("init")
  try:
    paths = RitPaths.build_rit_paths(os.getcwd(), init=True)
    logger.info("Successfully created rit directory: %s", paths.rit_dir)
    return 0

  except FileExistsError:
    paths = RitPaths.build_rit_paths(os.getcwd())
    logger.error("The rit directory already exists: %s", paths.rit_dir)
    return 1

def commit(*, msg: str):
  logger.debug('commit')
  logger.debug('  msg: %s', msg)

  paths = get_paths()
  create_commit(paths, time.time(), msg)

def checkout(*, ref: str, force: bool):
  logger.debug('checkout')
  logger.debug('  ref: %s', ref)
  logger.debug('  force: %s', force)

  paths = get_paths()

def branch(*, name: str, ref: Optional[str], force: bool):
  '''
  ref is a ref name or commit id or head_ref_name
  '''
  logger.debug('branch')
  logger.debug('  name: %s', name)
  logger.debug('  ref: %s', ref)
  logger.debug('  force: %s', force)

  paths = get_paths()

  if is_branch(name) and not force:
    raise RitError('Branch already exists. Use -f to force the overwrite of it.', name)

  if ref is None:
    # create branch at head
    head_commit_id = get_head_commit_id(paths)
    if head_commit_id is None:
      logger.warning("There is no current commit. Aborting.")
      return 1
    write_branch(paths, name, head_commit_id)
    return

  res = resolve_ref(paths, ref)
  if res is None:
    raise RitError("Unable to find reference: %s", ref)

  commit_id, is_ref_branch = res
  logger.debug("Reference was branch? %s", is_ref_branch)
  write_branch(paths, name, commit_id)

def log(*, ref: str, all: bool, oneline: bool):
  logger.debug('log')
  logger.debug('  ref: %s', ref)
  logger.debug('  all: %s', all)
  logger.debug('  oneline: %s', oneline)

  paths = get_paths()

def reflog():
  logger.debug('reflog')

  paths = get_paths()

  raise NotImplementedError()

def prune():
  # Prune lost branches
  logger.debug('prune')

  paths = get_paths()

  raise NotImplementedError()

def reroot():
  # Move the root to the latest common ancestor of all branches
  logger.debug('reroot')

  paths = get_paths()

  raise NotImplementedError()


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
  parser.add_argument('-r', '--ref', help="The head of the new branch. By default, the current commit is used.")
  parser.add_argument('-f', '--force', action='store_true', help="The head of the new branch. By default, the current commit is used.")
  args = parser.parse_args(argv)
  return branch(**vars(args))

def log_main(argv, prog):
  parser = argparse.ArgumentParser(description="Log the current commit history", prog=prog)
  parser.add_argument('-r', '--ref', default=head_ref_name, help="The head of the branch to log. By default, the current commit is used.")
  parser.add_argument('--all', action='store_true', help="Include all branches")
  parser.add_argument('--oneline', action='store_true', help="Show commits with a single line")
  args = parser.parse_args(argv)
  return log(**vars(args))

command_handlers = dict(
  init = init_main,
  commit = commit_main,
  checkout = checkout_main,
  branch = branch_main,
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

  logging.addLevelName(logging.DEBUG, color_section.format(30 + blue, logging.getLevelName(logging.DEBUG)[0]))
  logging.addLevelName(logging.INFO, color_section.format(30 + green, logging.getLevelName(logging.INFO)[0]))
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
  try:
    return command_handlers[args.command](sub_argv, prog=f'{parser.prog} {args.command}')
  except RitError as exc:
    logger.error(exc.msg, *exc.args)

if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))
