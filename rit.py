#!/usr/bin/env python

import argparse
import datetime
import hashlib
import json
import logging
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from typing import Optional, Tuple

''' GLOBALS '''

logger = logging.getLogger(__name__)
rit_dir_name = '.rit'
default_branch_name = 'main'
head_ref_name = 'HEAD'
short_hash_index = 7
fg = 30
bg = 40
black, red, green, yellow, blue, magenta, cyan, white = range(8)

''' STRUCTS '''

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

@dataclass
class Commit:
  parent_commit_id: Optional[str]
  commit_id: str
  create_time: float
  msg: str

  def __post_init__(self):
    check_obj_types(self, dict(
      parent_commit_id = optional_t(exact_t(str)),
      commit_id = exact_t(str),
      create_time = exact_t(float),
      msg = exact_t(str),
    ))

@dataclass
class Branch:
  name: str
  commit_id: str

  def __post_init__(self):
    check_obj_types(self, dict(
      name = exact_t(str),
      commit_id = exact_t(str),
    ))

@dataclass
class HeadNode:
  commit_id: Optional[str]
  branch_name: Optional[str]

  def __post_init__(self):
    check_obj_types(self, dict(
      commit_id = optional_t(exact_t(str)),
      branch_name = optional_t(exact_t(str)),
    ))
    if (self.commit_id is None) == (self.branch_name is None):
      raise TypeError("HEAD must be a branch name or a commit id")

class RitError(Exception):
  def __init__(self, msg, *args):
    super(RitError, self).__init__()
    self.msg = msg
    self.args = args


''' UTIL '''

def colorize(color: int, msg: str):
  reset_seq = "\033[0m"
  color_seq = "\033[1;{}m"

  color_section = color_seq + "{}" + reset_seq

  return color_section.format(color, msg)

def mkdir(*args, exists_ok=False, **kwargs):
  try:
    os.mkdir(*args, **kwargs)
  except FileExistsError:
    if not exists_ok:
      raise

def exact_t(*types):
  def exact_type(obj):
    return isinstance(obj, types)
  return exact_type

def optional_t(obj_t):
  def optional_type(obj):
    if obj is None:
      return True
    else:
      return obj_t(obj)
  return optional_type

def list_t(obj_t):
  def list_type(obj):
    if isinstance(obj, list):
      return all(obj_t(val) for val in obj)
    return False
  return list_type

def check_types(**type_defs):
  for name, (obj, type_def) in type_defs.items():
    if not type_def(obj):
      raise TypeError(f"Element had invalid type: {name}: {type(obj)}")

def check_obj_types(obj, type_defs):
  objs = {}
  for key, type_def in type_defs.items():
    objs[key] = (getattr(obj, key), type_def)

def require(statement, msg, *args):
  if not statement:
    raise RitError(msg, *args)


''' RIT DIR HELPERS '''

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
  return RitPaths.build_rit_paths(cwd)

def get_tar_path(paths: RitPaths, commit_id: str):
  return os.path.join(paths.backups, commit_id + '.tar')

def get_snar_path(paths: RitPaths, commit_id: str):
  return os.path.join(paths.backups, commit_id + '.snar')


''' COMMIT HELPERS '''

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
    return Commit(**dict(**json.load(fin), commit_id=commit_id))

def write_commit(paths: RitPaths, commit: Commit):
  logger.debug("Creating commit entry: %s", commit.commit_id)
  with open(os.path.join(paths.commits, commit.commit_id), 'w') as fout:
    data = asdict(commit)
    del data['commit_id']
    json.dump(data, fout)

def is_commit(paths: RitPaths, commit_id: str):
  try:
    read_commit(paths, commit_id)
    return True
  except FileNotFoundError:
    return False

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

  logger.debug("Calling tar")
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
  return commit


''' HEAD HELPERS '''

def read_head(paths: RitPaths):
  try:
    with open(os.path.join(paths.rit_dir, head_ref_name)) as fin:
      return HeadNode(**json.load(fin))
  except FileNotFoundError:
    return HeadNode(None, default_branch_name)

def write_head(paths: RitPaths, head: HeadNode):
  with open(os.path.join(paths.rit_dir, head_ref_name), 'w') as fout:
    json.dump(asdict(head), fout)

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

def update_head(paths, commit_id, head = None):
  if head is None:
    head = read_head(paths)
  if head.commit_id is not None:
    head.commit_id = commit_id
  else:
    write_branch(paths, head.branch_name, commit_id)
  write_head(paths, head)


''' RESET HELPERS '''

def reset(paths: RitPaths, commit_id: str):
  logger.debug('resetting to %s', commit_id)


''' BRANCH HELPERS '''

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
    branch = json.load(fin)
    logger.debug("Branch data: %s", branch)
    return Branch(**dict(**branch, name=name))

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
    return read_commit(paths, ref.commit_id), True
  except FileNotFoundError:
    pass
  raise RitError("Found a reference, but couldn't locate the commit!")

def is_branch(paths: RitPaths, name: str):
  try:
    read_branch(paths, name)
    return True
  except FileNotFoundError:
    return False

def get_branches(paths: RitPaths):
  for _, _, branches in os.walk(paths.branches):
    return branches
  return []

branch_name_re = re.compile('^\\w+$')
def validate_branch_name(name: str):
  if branch_name_re.search(name) is None:
    raise RitError("Invalid branch name: %s", name)

def get_commit_ids_to_branches_map(paths: RitPaths):
  branches = get_branches(paths)
  commit_ids_to_branches: dict[str, list[Branch]] = {}
  for branch_name in branches:
    branch = read_branch(paths, branch_name)
    if branch.commit_id not in commit_ids_to_branches:
      commit_ids_to_branches[branch.commit_id] = [branch]
    else:
      commit_ids_to_branches[branch.commit_id].append(branch)
  return commit_ids_to_branches

def pprint_dur(dur: int, name: str):
  return f"{dur} {name}{'s' if dur > 1 else ''}"

def pprint_time_duration(start: float, end: float):
  start_dt = datetime.datetime.fromtimestamp(start)
  end_dt = datetime.datetime.fromtimestamp(end)
  dur = end - start
  dur_sec = dur
  dur_min = dur / 60
  dur_hour = dur_min / 60
  dur_day = dur_hour / 24
  dur_month = 12 * (end_dt.year - start_dt.year) + (end_dt.month - start_dt.month)
  dur_year = dur_month // 12

  parts = []
  if dur_year >= 5:
    parts.append(pprint_dur(int(dur_year), 'year'))
  elif dur_year >= 1:
    parts.append(pprint_dur(int(dur_year), 'year'))
    parts.append(pprint_dur(int(dur_month) % 12, 'month'))
  elif dur_month >= 1:
    parts.append(pprint_dur(int(dur_month) % 12, 'month'))
  elif dur_day >= 1:
    parts.append(pprint_dur(int(dur_day), 'day'))
  elif dur_hour >= 1:
    parts.append(pprint_dur(int(dur_hour) % 60, 'hour'))
  elif dur_min >= 1:
    parts.append(pprint_dur(int(dur_min) % 60, 'minute'))
  elif dur_sec >= 20:
    parts.append(pprint_dur(int(dur_sec) % 60, 'second'))
  else:
    return 'Just now'
  return ', '.join(parts) + ' ago'

''' SUB LOG COMMANDS '''

def log_commit(paths: RitPaths, commit_id: str):
  head_commit = read_commit(paths, commit_id)
  # map to commit_id to parent commit object
  commit_map = {}

  commit = head_commit
  while commit.parent_commit_id is not None:
    if commit.parent_commit_id in commit_map:
      break
    parent_commit = read_commit(paths, commit.parent_commit_id)
    commit_map[commit.commit_id] = parent_commit
    commit = parent_commit

  commit_ids_to_branches = get_commit_ids_to_branches_map(paths)

  now = time.time()
  commit = head_commit
  while commit is not None:
    colored_commit_id = colorize(fg + yellow, commit.commit_id[:short_hash_index])

    if commit.commit_id in commit_ids_to_branches:
      branches = commit_ids_to_branches[commit.commit_id]
      colored_branch_names = map(lambda branch: colorize(fg + green, branch.name), branches)
      branch_details = f"({', '.join(colored_branch_names)}) "
    else:
      branch_details = ''

    time_duration = pprint_time_duration(commit.create_time, now)
    date_details = f'({time_duration}) '

    logger.info("* %s %s%s%s", colored_commit_id, date_details, branch_details, commit.msg)
    commit = commit_map.get(commit.commit_id)

''' SUB BRANCH COMMANDS '''

def delete_branch(paths: RitPaths, name: str):
  try:
    os.remove(os.path.join(paths.branches, name))
  except FileNotFoundError:
    raise RitError("Branch not found: %s", name)


def list_branches(paths: RitPaths):
  head = read_head(paths)
  for branch_name in get_branches(paths):
    this_sym = '*' if branch_name == head.branch_name else ' '
    branch = read_branch(paths, branch_name)
    commit = read_commit(paths, branch.commit_id)
    colored_commit_id = colorize(fg + yellow, branch.commit_id[:short_hash_index])
    colored_branch_name = colorize(fg + green, branch_name)
    logger.info("%s %s\t%s %s", this_sym, colored_branch_name, colored_commit_id, commit.msg)

def get_head_or_ref(paths: RitPaths, ref: Optional[str]):
  '''
  Returns None if head has no commits, or if ref was not found.
  Returns commit_id, is_ref_branch otherwise.
  '''
  if ref is None:
    # get commit id of head
    head_commit_id = get_head_commit_id(paths)
    if head_commit_id is None:
      return None
    else:
      return head_commit_id, False

  else:
    # get commit id of ref
    res = resolve_ref(paths, ref)
    if res is None:
      return None

    commit, is_ref_branch = res
    return commit.commit_id, is_ref_branch

def create_branch(paths: RitPaths, name: str, ref: Optional[str], force: bool):
  if is_branch(paths, name) and not force:
    raise RitError('Branch already exists: %s. Use -f to force the overwrite of it.', name)

  res = get_head_or_ref(paths, ref)
  if res is None:
    if ref is None:
      raise RitError("No current commit to create branch for.")
    else:
      raise RitError("Unable to locate commit for provided ref: %s", ref)
  logger.info("Resolved ref: %s: %s", ref, res)
  commit_id, is_ref_branch = res
  write_branch(paths, name, commit_id)
  logger.info("Created branch %s at %s", name, commit_id[:short_hash_index])


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
  check_types(
    msg = (msg, exact_t(str)),
  )

  paths = get_paths()
  commit = create_commit(paths, time.time(), msg)
  logger.info("Created commit %s: %s", commit.commit_id[:short_hash_index], commit.msg)

def checkout(*, ref: str, force: bool):
  logger.debug('checkout')
  logger.debug('  ref: %s', ref)
  logger.debug('  force: %s', force)
  check_types(
    ref = (ref, optional_t(exact_t(str))),
    force = (force, exact_t(bool)),
  )

  paths = get_paths()
  res = resolve_ref(paths, ref)
  if res is None:
    raise RitError("Unable to resolve ref")
  commit, is_ref_branch = res
  commit_id = commit.commit_id
  head = read_head(paths)
  if is_ref_branch:
    head.branch_name = ref
    head.commit_id = None
  else:
    head.branch_name = None
    head.commit_id = commit_id
  update_head(paths, commit_id, head)
  reset(paths, commit_id)

def branch(*, name: Optional[str], ref: Optional[str], force: bool, delete: bool):
  '''
  ref is a ref name or commit id or head_ref_name
  '''
  logger.debug('branch')
  logger.debug('  name: %s', name)
  logger.debug('  ref: %s', ref)
  logger.debug('  force: %s', force)
  logger.debug('  delete: %s', force)
  check_types(
    name = (name, optional_t(exact_t(str))),
    ref = (ref, optional_t(exact_t(str))),
    force = (force, exact_t(bool)),
    delete = (delete, exact_t(bool)),
  )

  paths = get_paths()

  if delete:
    if force:
      raise RitError("You can't force delete branches")
    elif name is None:
      raise RitError("You must specify a branch to delete")
    elif ref is not None:
      raise RitError("You can't specify a reference branch with the delete option")

    return delete_branch(paths, name)

  elif name is None:
    if force:
      raise RitError("You cannot specify force while listing branches")
    elif ref is not None:
      raise RitError("You cannot specify a ref branch while listing branches")

    return list_branches(paths)

  else:
    validate_branch_name(name)

    return create_branch(paths, name, ref, force)

def log(*, ref: Optional[str], all: bool):
  logger.debug('log')
  logger.debug('  ref: %s', ref)
  logger.debug('  all: %s', all)
  check_types(
    ref = (ref, optional_t(exact_t(str))),
    all = (all, exact_t(bool)),
  )

  paths = get_paths()

  if all:
    raise NotImplementedError()

  res = get_head_or_ref(paths, ref)
  if res is None:
    if ref is None:
      logger.info("No commits in history.")
    else:
      raise RitError("Unable to locate commit for provided ref: %s", ref)
  commit_id, is_ref_branch = res
  log_commit(paths, commit_id)

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
  parser.add_argument('name', nargs='?', help="The name of the branch to create. If omitted, lists all branches.")
  parser.add_argument('ref', nargs='?', help="The head of the new branch. By default, the current commit is used.")
  parser.add_argument('-f', '--force', action='store_true', help="The head of the new branch. By default, the current commit is used.")
  parser.add_argument('-d', '--delete', action='store_true', help="Delete the specified branch.")
  args = parser.parse_args(argv)
  return branch(**vars(args))

def log_main(argv, prog):
  parser = argparse.ArgumentParser(description="Log the current commit history", prog=prog)
  parser.add_argument('ref', nargs='?', help="The head of the branch to log. By default, the current commit is used.")
  parser.add_argument('--all', action='store_true', help="Include all branches")
  args = parser.parse_args(argv)
  return log(**vars(args))

command_handlers = dict(
  init = init_main,
  commit = commit_main,
  checkout = checkout_main,
  branch = branch_main,
  log = log_main,
)


''' MAIN '''

def setup_logger(verbose: int):
  if verbose == -1:
    level = logging.WARNING
  elif verbose == 0:
    level = logging.INFO
  else:
    level = logging.DEBUG

  format = "%(levelname)s: %(message)s"

  logging.basicConfig(level=level, format=format)

  logging.addLevelName(logging.DEBUG, colorize(fg + blue, logging.getLevelName(logging.DEBUG)[0]))
  logging.addLevelName(logging.INFO, colorize(fg + green, logging.getLevelName(logging.INFO)[0]))
  logging.addLevelName(logging.WARNING, colorize(fg + yellow, logging.getLevelName(logging.WARNING)[0]))
  logging.addLevelName(logging.ERROR, colorize(fg + red, logging.getLevelName(logging.ERROR)[0]))

def main(argv):
  parser = argparse.ArgumentParser(description="A raw version control system", add_help=False)
  parser.add_argument('command', choices=command_handlers.keys())
  parser.add_argument('--verbose', '-v', help="Increase logging level. Default level is info.", action='count', default=0)
  parser.add_argument('--quiet', '-q', help="Decrease logging level. Default level is info.", action='count', default=0)
  args, sub_argv = parser.parse_known_args(argv)
  logger.debug("Parsed args: %s", args)
  logger.debug("Extra args: %s", sub_argv)
  setup_logger(args.verbose - args.quiet)
  try:
    return command_handlers[args.command](sub_argv, prog=f'{parser.prog} {args.command}')
  except RitError as exc:
    logger.error(exc.msg, *exc.args)
    return 1

if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))
