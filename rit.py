#!/usr/bin/env python

import json
import time
import argparse
import hashlib
import logging
import os
import sys
from dataclasses import asdict, dataclass
from typing import Optional, Union


logger = logging.getLogger(__name__)
rit_dir_name = '.rit'
default_branch_name = 'main'

''' UTILS '''

def hash_bytes(data: bytes):
  return hashlib.sha1(data).hexdigest()

def hash_file(file: str):
  with open(file, 'rb') as fin:
    # TODO: we might not be able to read backup tar files into memory. Need on
    # the fly hashing.
    return hash_bytes(fin.read())

def mkdir(path: str):
  os.makedirs(path, exists_ok=True)

def rmfile(path: str):
  try:
    os.remove(path)
  except FileNotFoundError:
    pass  # good
  except Exception:
    logger.error("Tried to remove file but it failed: %s", path, exc_info=True)

def rmdir(path: str):
  try:
    os.rmdir(path)
  except FileNotFoundError:
    pass  # good
  except Exception:
    logger.error("Unable to remove directory: %s", path, exc_info=True)


''' FS STRUCTS '''

@dataclass
class RitPaths:
  root: str
  ''' The directory to backup is stored here '''

  rit_dir: str
  ''' All rit information is stored here '''

  refs: str
  '''
  Named references are stored here. The filename is the branch name, tag name or
  HEAD. HEAD is reserved for where the current working directory is.
  '''

  commits: str
  ''' Commit info is stored here. The filename is commit_id. '''

  backups: str
  ''' Backups are stored here, full and partial.  '''

  work: str
  ''' A place to temporarily store files '''

  @staticmethod
  def build_rit_paths(root: str):
    root = os.path.realpath(root)
    rit_dir = os.path.join(root, rit_dir_name)
    refs = os.path.join(rit_dir, 'refs')
    commits = os.path.join(rit_dir, 'commits')
    backups = os.path.join(rit_dir, 'backups')
    work = os.path.join(rit_dir, 'work')
    return RitPaths(
      root = root,
      rit_dir = rit_dir,
      refs = refs,
      commits = commits,
      backups = backups,
      work = work,
    )

''' STRUCTS '''

@dataclass
class RefNode:
  parent_ref_id: Optional[str]
  ref_id: str
  create_time: float
  msg: str

@dataclass
class BranchNode:
  name: str
  ref_id: str

@dataclass
class HeadNode:
  ref_id: Optional[str]
  branch_name: Optional[str]

  def __post_init__(self):
    assert (self.ref_id is None) != (self.branch_name is None), "HEAD must be a branch or ref id"

@dataclass
class TagNode:
  name: str
  ref_id: str

@dataclass
class RefTree:
  head: HeadNode
  branch_nodes: list[BranchNode]
  tag_nodes: list[TagNode]

class RitError(Exception):
  def __init__(self, msg, *args):
    super(RitError, self).__init__()
    self.msg = msg
    self.args = args


''' MANAGERS '''

def get_paths():
  cwd = os.path.realpath(os.getcwd())
  rit_dir = os.path.join(cwd, rit_dir_name)
  last_cwd = None
  while not os.path.isdir(rit_dir):
    last_cwd = cwd
    cwd = os.path.dirname(cwd)
    if last_cwd == cwd:
      raise RitError("Unable to locate rit directory")
    rit_dir = os.path.join(cwd, rit_dir_name)
  return RitPaths.build_rit_paths(rit_dir)

def check_work_dir(paths: RitPaths):
  _, dirs, files = next(os.walk(paths.work))
  assert not dirs and not files, "Dirty work directory. Is another rit command running?"

def get_head(paths: RitPaths):
  try:
    with open(os.path.join(paths.refs, 'HEAD')) as fin:
      return HeadNode(**json.loads(fin))
  except FileNotFoundError:
    return HeadNode(None, default_branch_name)
  except Exception:
    logger.error("Unable to get current HEAD. Switching back to main branch.")
    return HeadNode(None, default_branch_name)

def get_tar_path(paths: RitPaths, ref_id: str):
  return os.path.join(paths.backups, ref_id + '.tar')

def get_snar_path(paths: RitPaths, ref_id: str):
  return os.path.join(paths.backups, ref_id + '.snar')

def get_branch_ref_id(paths: RitPaths, branch_name: str):
  try:
    with open(os.path.join(paths.refs, branch_name)) as fin:
      return fin.read().strip()
  except FileNotFoundError:
    return None
  except Exception:
    logger.error("Unable to get branch for unexpected reasons.")
    raise

def get_head_ref_id(paths: RitPaths, head: HeadNode):
  if head.ref_id is not None:
    return head.ref_id
  else:
    return get_branch_ref_id(paths, head.branch_name)

def write_ref_node(paths: RitPaths, ref_node: RefNode):
  pass

def hash_ref(create_time: float, msg: str, snar: str, tar: str):
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

def write_head(paths: RitPaths, head: HeadNode):
  with open(os.path.join(paths.refs, 'HEAD'), 'w') as fout:
    json.dump(asdict(head), fout)

def write_branch(paths: RitPaths, branch_name: str, ref_id: str):
  with open(os.path.join(paths.refs, branch_name), 'w') as fout:
    fout.write(ref_id)

def create_ref(paths: RitPaths, create_time: float, msg: str):
  head = get_head(paths)
  parent_ref_id = get_head_ref_id(paths)
  logger.debug("Parent ref: %s", parent_ref_id)

  work_tar = os.path.join(paths.work, 'ref.tar')
  logger.debug("Creating tar: %s", work_tar)

  work_snar = os.path.join(paths.work, 'ref.snar')
  logger.debug("Creating snar: %s", work_snar)

  tar_cmd = ['tar', '-cg', work_snar, '-f', work_tar, paths.root, f'--exclude={rit_dir_name}']
  logger.debug("Tar command: %s", tar_cmd)

  logger.debug("Creating work directory")
  mkdir(paths.work)

  if parent_ref_id is not None:
    head_snar = get_snar_path(paths, parent_ref_id)
    logger.debug("Copying previous snar: %s", head_snar)
    with open(head_snar, 'rb') as fin:
      with open(work_snar, 'wb') as fout:
        # TODO: This probably doesn't work with large files, and there might
        # be a better way to copy
        fout.write(fin.read())
  else:
    logger.debug("Using fresh snar file since no parent ref")

  logger.debug("Creating ref backup and snar")
  # TODO: call tar instead
  with open(work_snar, 'w') as fout:
    fout.write(f"This is a snar test {create_time}\n")
  with open(work_tar, 'w') as fout:
    fout.write(f"This is a tar test {create_time}\n")

  ref_id = hash_ref(create_time, msg, work_snar, work_tar)

  logger.debug("Moving working snar into backups directory")
  snar = os.path.join(paths.backups, ref_id + '.snar')
  os.rename(work_snar, snar)

  logger.debug("Moving working tar into backups directory")
  tar = os.path.join(paths.backups, ref_id + '.tar')
  os.rename(work_tar, tar)

  with open(os.path.join(paths.commits, ref_id), 'w') as fout:
    json.dump(dict(parent_ref_id=parent_ref_id, create_time=create_time, msg=msg), fout)

  if head.ref_id is not None:
    head.ref_id = ref_id
    write_head(paths, head)
  else:
    write_branch(paths, head.branch_name, ref_id)

  return ref_id

''' API '''

def init():
  logger.debug("init")
  paths = RitPaths.build_rit_paths(os.getcwd())
  try:
    os.makedirs(paths.rit_dir)
  except FileExistsError:
    logger.error("The rit directory already exists: %s", paths.rit_dir)
    return 1
  logger.info("Successfully created rit directory: %s", paths.rit_dir)

def commit(*, msg: str):
  logger.debug('commit')
  logger.debug('  msg: %s', msg)

  paths = get_paths()
  ref = create_ref(paths, time.time(), msg)

def checkout(*, ref: str, force: bool):
  logger.debug('checkout')
  logger.debug('  ref: %s', ref)
  logger.debug('  force: %s', force)

  paths = get_paths()

def branch(*, name: str, ref: str, force: bool):
  logger.debug('branch')
  logger.debug('  name: %s', name)
  logger.debug('  ref: %s', ref)
  logger.debug('  force: %s', force)

  paths = get_paths()

def tag(*, name: str, ref: str, force: bool):
  logger.debug('tag')
  logger.debug('  name: %s', name)
  logger.debug('  ref: %s', ref)
  logger.debug('  force: %s', force)

  paths = get_paths()

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
  # Prune lost refs
  logger.debug('prune')

  paths = get_paths()

  raise NotImplementedError()

def reroot():
  # Move the root to the latest common ancestor of all tags and branches
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
