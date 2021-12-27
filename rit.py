#!/usr/bin/env python

import subprocess
import shutil
import copy
import argparse
import datetime
import hashlib
import json
import logging
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Optional
from collections import defaultdict

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

  info: str = ''
  '''
  Eventually, this'll store something like where the full backup archive is.
  '''

  def __post_init__(self):
    check_obj_types(self, dict(
      name = exact_t(str),
      commit_id = exact_t(str),
    ))

@dataclass
class HeadNode:
  commit_id: Optional[str] = None
  branch_name: Optional[str] = None

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

@dataclass
class RitCache:
  _paths: RitPaths = None
  _head: HeadNode = None
  _commits: dict[str, Commit] = field(default_factory=dict)
  _branches: dict[str, Branch] = field(default_factory=dict)
  _branch_name_to_commit_ids: dict[str, str] = None
  _commit_id_to_branch_names: dict[str, list[str]] = None
  _branch_names: list[str] = None
  _commit_ids: list[str] = None
  _short_commit_tree: dict[str, list[str]] = None

  def clear(self):
    ''' If the rit directory is modified, then the cache must be cleared '''
    self._head = None
    self._commits = {}
    self._branches = {}
    self._branch_name_to_commit_ids = None
    self._commit_id_to_branch_names = None
    self._branch_names = None
    self._commit_ids = None
    self._short_commit_tree = None

  ''' SET '''

  def set_commit(self, commit: Commit):
    self._write_commit(commit)
    self.clear()

  def set_branch(self, branch: Branch):
    self._write_branch(branch)
    self.clear()

  def set_head(self, head: HeadNode):
    self._write_head(head)
    self._head = None

  ''' GET '''

  @property
  def paths(self):
    if self._paths is None:
      self._paths = self._read_paths()
    return self._paths

  @property
  def head(self):
    if self._head is None:
      self._head = self._read_head()
    return self._head

  def get_head_commit_id(self):
    head = self.head
    if head.commit_id is not None:
      return head.commit_id
    else:
      branch = self.get_branch(head.branch_name)
      if branch is not None:
        return branch.commit_id
      else:
        return None

  def get_commit_ids(self):
    if self._commit_ids is None:
      self._commit_ids = self._read_commit_ids()
    return self._commit_ids

  def get_commit(self, commit_id: str, *, ensure=False):
    if commit_id not in self._commits:
      try:
        self._commits[commit_id] = self._read_commit(commit_id)
      except FileNotFoundError:
        if ensure:
          raise RitError("Unable to load expected commit")
        return None
    return self._commits[commit_id]

  def is_commit(self, commit_id: str):
    return self.get_commit(commit_id) is not None

  def get_branch_names(self):
    if self._branch_names is None:
      self._branch_names = self._read_branch_names()
    return self._branch_names

  def get_branch(self, name: str, *, ensure=False):
    if name not in self._branches:
      try:
        self._branches[name] = self._read_branch(name)
      except FileNotFoundError:
        if ensure:
          raise RitError("Unable to load expected branch")
        return None
    return self._branches[name]

  def is_branch(self, name: str):
    return self.get_branch(name) is not None

  def populate_commit_to_branch_map(self):
    branch_names = self.get_branch_names()
    self._branch_name_to_commit_ids = {}
    self._commit_id_to_branch_names = defaultdict(list)
    for branch_name in branch_names:
      branch = self.get_branch(branch_name, ensure=True)
      commit_id = branch.commit_id
      self._branch_name_to_commit_ids[branch_name] = commit_id
      self._commit_id_to_branch_names[commit_id].append(branch_name)
    head_commit_id = self.get_head_commit_id()
    if head_commit_id is not None:
      self._branch_name_to_commit_ids[head_ref_name] = head_commit_id
      self._commit_id_to_branch_names[head_commit_id].append(head_ref_name)

  def get_branch_name_to_commit_ids(self):
    if self._branch_name_to_commit_ids is None:
      self.populate_commit_to_branch_map()
    return self._branch_name_to_commit_ids

  def get_commit_id_to_branch_names(self):
    if self._commit_id_to_branch_names is None:
      self.populate_commit_to_branch_map()
    return self._commit_id_to_branch_names

  def get_commit_tree(self):
    if self._short_commit_tree is None:
      self._short_commit_tree = defaultdict(list)
      for commit_id in self.get_commit_ids():
        self._short_commit_tree[commit_id[:short_hash_index]].append(commit_id)
    return self._short_commit_tree

  ''' IO '''

  def _read_paths(self):
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

  def _read_head(self):
    try:
      with open(os.path.join(self.paths.rit_dir, head_ref_name)) as fin:
        return HeadNode(**json.load(fin))
    except FileNotFoundError:
      return HeadNode(None, default_branch_name)

  def _read_commit(self, commit_id: str):
    logger.debug("Reading commit: %s", commit_id)
    with open(os.path.join(self.paths.commits, commit_id)) as fin:
      return Commit(**dict(**json.load(fin), commit_id=commit_id))

  def _write_commit(self, commit: Commit):
    logger.debug("Writing commit: %s", commit.commit_id)
    with open(os.path.join(self.paths.commits, commit.commit_id), 'w') as fout:
      data = asdict(commit)
      del data['commit_id']
      json.dump(data, fout)

  def _read_branch(self, name: str):
    logger.debug("Reading branch: %s", name)
    with open(os.path.join(self.paths.branches, name)) as fin:
      branch = json.load(fin)
      return Branch(**dict(**branch, name=name))

  def _write_branch(self, branch: Branch):
    logger.debug("Writing branch %s to %s", branch.name, branch.commit_id)
    if self.is_commit(branch.name):
      raise RitError('Not creating a branch with the same name as a commit id: %s', branch.name)
    data = asdict(branch)
    del data['name']
    with open(os.path.join(self.paths.branches, branch.name), 'w') as fout:
      json.dump(data, fout)

  def _read_branch_names(self):
    for _, _, branch_names in os.walk(self.paths.branches):
      return branch_names
    return []

  def _read_commit_ids(self):
    for _, _, commit_ids in os.walk(self.paths.commits):
      return commit_ids
    return []

  def _write_head(self, head: HeadNode):
    with open(os.path.join(self.paths.rit_dir, head_ref_name), 'w') as fout:
      json.dump(asdict(head), fout)


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

def get_tar_path(rit: RitCache, commit_id: str):
  return os.path.join(rit.paths.backups, commit_id + '.tar')

def get_snar_path(rit: RitCache, commit_id: str):
  return os.path.join(rit.paths.backups, commit_id + '.snar')


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

def check_tar():
  logger.debug("Checking tar version")
  process = subprocess.Popen(['tar', '--version'], stdout=subprocess.PIPE)
  contents = process.stdout.read()
  process.wait()
  version = contents.decode('utf-8').split('\n', 1)[0]
  logger.debug("Tar Version: %s", version)
  assert 'GNU tar' in version, "You must have a GNU tar installed"

def create_commit_tar(*,
      rit: RitCache,
      work_tar: str,
      parent_commit_id: Optional[str],
      verbose: bool,
      compress: bool):
  logger.debug("Parent ref: %s", parent_commit_id)
  logger.debug("Working tar: %s", work_tar)

  work_snar = os.path.join(rit.paths.work, 'ref.snar')
  logger.debug("Working snar: %s", work_snar)

  if parent_commit_id is not None:
    head_snar = get_snar_path(rit, parent_commit_id)
    logger.debug("Copying previous snar: %s", head_snar)
    shutil.copyfile(head_snar, work_snar)
  else:
    logger.debug("Using fresh snar file since no parent commit")

  check_tar()
  opts = '-c'
  if verbose:
    opts += 'v'
  if compress:
    opts += 'z'
  opts += 'g'
  tar_cmd = ['tar', opts, work_snar, f'--exclude={rit_dir_name}', '-f', work_tar, '.']
  logger.debug("Running tar command: %s", tar_cmd)

  if verbose:
    process = subprocess.Popen(tar_cmd, cwd=rit.paths.root, stdout=subprocess.PIPE)
    # TODO: doesn't forward SIGTERM, only SIGINT
    line = process.stdout.readline()
    lines = []
    while line:
      if line != b'./\n':
        if len(lines) < 20:
          lines.append(line)
        sys.stdout.buffer.write(line)
      line = process.stdout.readline()
  else:
    process = subprocess.Popen(tar_cmd, cwd=rit.paths.root)
    lines = None
  exit_code = process.wait()
  if exit_code != 0:
    raise RitError("Creating commit's tar failed with exit code: %d", exit_code)

  return work_snar, lines

def create_commit(rit: RitCache, create_time: float, msg: str):
  work_tar = os.path.join(rit.paths.work, 'ref.tar')
  parent_commit_id = rit.get_head_commit_id()
  compress = True
  verbose = logger.getEffectiveLevel() <= logging.DEBUG
  work_snar, _ = create_commit_tar(rit=rit, parent_commit_id=parent_commit_id, work_tar=work_tar, verbose=verbose, compress=compress)

  commit_id = hash_commit(create_time, msg, work_snar, work_tar)

  logger.debug("Moving working snar into backups directory")
  snar = get_snar_path(rit, commit_id)
  os.rename(work_snar, snar)

  logger.debug("Moving working tar into backups directory")
  tar = get_tar_path(rit, commit_id)
  os.rename(work_tar, tar)

  commit = Commit(parent_commit_id, commit_id, create_time, msg)
  rit.set_commit(commit)
  head = copy.copy(rit.head)
  if head.commit_id is not None:
    head.commit_id = commit_id
  else:
    rit.set_branch(Branch(head.branch_name, commit_id))
  rit.set_head(head)
  return commit


''' RESET HELPERS '''

def reset(rit: RitCache, commit_id: str):
  logger.debug('resetting to %s', commit_id)


''' BRANCH HELPERS '''

@dataclass
class ResolvedRef:
  commit: Optional[Commit] = None
  '''
  if None:
    if head:
      head points to a branch with no commit
    else:
      ref doesn't refer to a branch or commit
  else:
    ref ultimately refers to this commit
  '''

  branch: Optional[Branch] = None
  '''
  if None:
    if head:
      head points to a commit.
      head points to a branch with no commit.
    else:
      ref doesn't refer to a branch
  else:
    if head:
      head points to this branch
    else:
      ref points to this branch
  '''

  head: Optional[HeadNode] = None
  '''
  if None:
    ref was provided and not the head
  else:
    ref was omitted or explicitly set to the head
  '''

def resolve_commit(rit: RitCache, partial_commit_id: str):
  logger.debug("Resolving commit: %s", partial_commit_id)
  commit = rit.get_commit(partial_commit_id)
  if commit is not None:
    return commit
  if len(partial_commit_id) < short_hash_index:
    return None
  short_commit_id = partial_commit_id[:short_hash_index]
  commit_tree = rit.get_commit_tree()
  if short_commit_id not in commit_tree:
    return None
  commit = None
  for commit_id in commit_tree[short_commit_id]:
    size = len(partial_commit_id)
    if partial_commit_id == commit_id[:size]:
      if commit is not None:
        raise RitError("Reference %s matched commits %s and %s", partial_commit_id, commit.commit_id, commit_id)
      commit = rit.get_commit(commit_id, ensure=True)
  return commit

def resolve_ref(rit: RitCache, ref: Optional[str]):
  logger.debug("Resolving ref: %s", ref)
  res = ResolvedRef()
  if ref is None or ref == head_ref_name:
    head = rit.head
    res.head = head

    if head.branch_name is not None:
      res.branch = rit.get_branch(head.branch_name)
      if res.branch is not None:
        res.commit = rit.get_commit(res.branch.commit_id)
    else:
      res.commit = rit.get_commit(head.commit_id)
  else:
    res.branch = rit.get_branch(ref)
    if res.branch is not None:
      res.commit = rit.get_commit(res.branch.commit_id)
    else:
      res.commit = resolve_commit(rit, ref)
  return res

branch_name_re = re.compile('^\\w+$')
def validate_branch_name(name: str):
  if name == head_ref_name:
    raise RitError("Branch can't be named the same as the head ref: %s", name)
  elif branch_name_re.search(name) is None:
    raise RitError("Invalid branch name: %s", name)

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

def log_commit(rit: RitCache, commits: list[Commit]):
  leafs = set()
  commit_graph = {}
  for commit in commits:
    if commit.commit_id not in commit_graph:
      leafs.add(commit.commit_id)
    while True:
      commit_graph[commit.commit_id] = commit.parent_commit_id
      if commit.parent_commit_id is None:
        break
      parent_commit = rit.get_commit(commit.parent_commit_id, ensure=True)
      if parent_commit.commit_id in leafs:
        leafs.remove(parent_commit.commit_id)

      commit = parent_commit

  now = time.time()
  commit_id_to_branch_names = rit.get_commit_id_to_branch_names()
  for commit_id in leafs:
    logger.info("Log branch from %s", commit_id[:short_hash_index])
    while commit_id is not None:
      commit = rit.get_commit(commit_id, ensure=True)

      colored_commit_id = colorize(fg + yellow, commit.commit_id[:short_hash_index])

      if commit.commit_id in commit_id_to_branch_names:
        branch_names = commit_id_to_branch_names[commit.commit_id]
        colored_branch_names = []
        for branch_name in branch_names:
          if branch_name == head_ref_name:
            colored_branch_names.append(colorize(fg + yellow, branch_name))
          else:
            colored_branch_names.append(colorize(fg + green, branch_name))
        branch_details = f"({', '.join(colored_branch_names)}) "
      else:
        branch_details = ''

      time_duration = pprint_time_duration(commit.create_time, now)
      date_details = f'({time_duration}) '

      logger.info("* %s %s%s%s", colored_commit_id, date_details, branch_details, commit.msg)
      commit_id = commit_graph[commit_id]

''' SUB BRANCH COMMANDS '''

def delete_branch(rit: RitCache, name: str):
  try:
    os.remove(os.path.join(rit.paths.branches, name))
    return True
  except FileNotFoundError:
    return False


def list_branches(rit: RitCache):
  head = rit.head
  for branch_name in rit.get_branch_names():
    this_sym = '*' if branch_name == head.branch_name else ' '
    branch = rit.get_branch(branch_name, ensure=True)
    commit = rit.get_commit(branch.commit_id, ensure=True)
    colored_commit_id = colorize(fg + yellow, branch.commit_id[:short_hash_index])
    colored_branch_name = colorize(fg + green, branch_name)
    logger.info("%s %s\t%s %s", this_sym, colored_branch_name, colored_commit_id, commit.msg)

def create_branch(rit: RitCache, name: str, ref: Optional[str], force: bool):
  if rit.is_branch(name) and not force:
    raise RitError('Branch already exists: %s. Use -f to force the overwrite of it.', name)

  res = resolve_ref(rit, ref)
  if res.commit is None:
    if res.head is not None:
      raise RitError("Current head doesn't have a commit")
    else:
      raise RitError("Unable to resolve ref: %s", ref)

  commit_id = res.commit.commit_id
  branch = Branch(name, commit_id)
  rit.set_branch(branch)
  logger.info("Created branch %s at %s", name, commit_id[:short_hash_index])

def log_refs(rit: RitCache, refs: list[str], all: bool, full: bool):
  commits = []

  if not refs:
    refs.append(None)
  if all:
    refs.extend(rit.get_branch_names())
  for ref in refs:
    res = resolve_ref(rit, ref)
    if res.commit is None:
      if res.head is not None:
        raise RitError("head branch doesn't have any commits")
      else:
        raise RitError("Unable to locate ref: %s", ref)
    commits.append(res.commit)

  log_commit(rit, commits)

def show_ref(rit: RitCache, ref: Optional[str]):
  res = resolve_ref(rit, ref)
  if res.commit is None:
    if res.head is not None:
      raise RitError("head branch doesn't have any commits to show")
    else:
      raise RitError("Unable to locate ref: %s", ref)

  tar_file = get_tar_path(rit, res.commit.commit_id)
  tar_cmd = ['tar', '-tf', tar_file]
  process = subprocess.Popen(tar_cmd)
  results = process.wait()
  if results != 0:
    logger.error("tar command failed with exit code %d", results)

def status_head(rit: RitCache):
  work_tar = os.devnull
  parent_commit_id = rit.get_head_commit_id()
  compress = False
  verbose = True
  work_snar, lines = create_commit_tar(rit=rit, parent_commit_id=parent_commit_id, work_tar=work_tar, verbose=verbose, compress=compress)
  os.remove(work_snar)
  if not lines:
    logger.info("Clean working directory!")


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

  rit = RitCache()
  commit = create_commit(rit, time.time(), msg)
  logger.info("Created commit %s: %s", commit.commit_id[:short_hash_index], commit.msg)

def checkout(*, ref: str, force: bool):
  logger.debug('checkout')
  logger.debug('  ref: %s', ref)
  logger.debug('  force: %s', force)
  check_types(
    ref = (ref, optional_t(exact_t(str))),
    force = (force, exact_t(bool)),
  )

  rit = RitCache()
  res = resolve_ref(rit, ref)
  if res.head is not None:
    raise RitError("Attempted to checkout head ref")
  elif res.commit is None:
    raise RitError("Unable to resolve ref to commit: %s", ref)
  commit_id = res.commit.commit_id
  reset(rit, commit_id)
  head = copy.copy(rit.head)
  if res.branch is not None:
    head.branch_name = res.branch.name
    head.commit_id = None
  else:
    head.branch_name = None
    head.commit_id = commit_id
  rit.set_head(head)

def branch(*, name: Optional[str], ref: Optional[str], force: bool, delete: bool):
  '''
  ref is a ref name or commit id or head_ref_name
  '''
  logger.debug('branch')
  logger.debug('  name: %s', name)
  logger.debug('  ref: %s', ref)
  logger.debug('  force: %s', force)
  logger.debug('  delete: %s', delete)
  check_types(
    name = (name, optional_t(exact_t(str))),
    ref = (ref, optional_t(exact_t(str))),
    force = (force, exact_t(bool)),
    delete = (delete, exact_t(bool)),
  )

  rit = RitCache()

  if name is not None:
    validate_branch_name(name)
    if rit.head.branch_name is not None and rit.head.branch_name == name:
      raise RitError("Unable to set commit of head branch.")

  if delete:
    if force:
      raise RitError("You can't force delete branches")
    elif name is None:
      raise RitError("You must specify a branch to delete")
    elif ref is not None:
      raise RitError("You can't specify a reference branch with the delete option")

    if not delete_branch(rit, name):
      raise RitError("Failed to remove branch since it didn't exist.")

  elif name is None:
    if force:
      raise RitError("You cannot specify force while listing branches")
    elif ref is not None:
      raise RitError("You cannot specify a ref branch while listing branches")

    return list_branches(rit)

  else:
    return create_branch(rit, name, ref, force)

def log(*, refs: list[str], all: bool, full: bool):
  logger.debug('log')
  logger.debug('  refs: %s', refs)
  logger.debug('  all: %s', all)
  logger.debug('  full: %s', all)
  check_types(
    refs = (refs, list_t(exact_t(str))),
    all = (all, exact_t(bool)),
  )

  rit = RitCache()
  log_refs(rit, refs, all, full)

def show(*, ref: Optional[str]):
  logger.debug('show')
  logger.debug('  ref: %s', ref)
  check_types(ref = (ref, optional_t(exact_t(str))))

  rit = RitCache()
  show_ref(rit, ref)

def status():
  logger.debug('status')

  rit = RitCache()
  status_head(rit)

def reflog():
  logger.debug('reflog')

  rit = RitCache()
  raise NotImplementedError()

def prune():
  # Prune lost branches
  logger.debug('prune')

  rit = RitCache()
  raise NotImplementedError()

def reroot():
  # Move the root to the latest common ancestor of all branches
  logger.debug('reroot')

  rit = RitCache()
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

def show_main(argv, prog):
  parser = argparse.ArgumentParser(description="Show contents of a commit", prog=prog)
  parser.add_argument('ref', nargs='?', help="The ref to show commit contents of. By default, head.")
  args = parser.parse_args(argv)
  return show(**vars(args))

def status_main(argv, prog):
  parser = argparse.ArgumentParser(description="Show the current directory's diff state.", prog=prog)
  args = parser.parse_args(argv)
  return status(**vars(args))

def log_main(argv, prog):
  parser = argparse.ArgumentParser(description="Log the current commit history", prog=prog)
  parser.add_argument('refs', nargs='*', help="The refs to log. By default, the current head is used.")
  parser.add_argument('--all', action='store_true', help="Include all branches")
  parser.add_argument('--full', action='store_true', help="Include more log data")
  args = parser.parse_args(argv)
  return log(**vars(args))

command_handlers = dict(
  init = init_main,
  commit = commit_main,
  checkout = checkout_main,
  branch = branch_main,
  show = show_main,
  status = status_main,
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
