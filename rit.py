#!/usr/bin/env python

from io import DEFAULT_BUFFER_SIZE
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
  ''' a class that represents the various directories used by rit '''

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
    '''
    Given a root rit directory, construct a rit paths object and ensure rit
    subdirectories exist. If init is True, the root rit path will be created.
    '''
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
  ''' represents a single commit '''

  parent_commit_id: Optional[str]
  ''' the commit id of parent, if any '''

  commit_id: str
  ''' the current commit's commit id '''

  create_time: float
  ''' the creation time of commit in seconds since posix '''

  msg: str
  ''' the commit msg'''

  def __post_init__(self):
    check_obj_types(self, dict(
      parent_commit_id = optional_t(exact_t(str)),
      commit_id = exact_t(str),
      create_time = exact_t(float),
      msg = exact_t(str),
    ))

@dataclass
class Branch:
  ''' represents a branch '''

  name: str
  ''' the branch name '''

  commit_id: str
  ''' the commit id tied to the branch '''

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
  '''
  The rit directory's current location. This is a branch or a commit. It is
  possible for a branch to be an orphan branch and have no commit, yet.

  Since commit_id or branch_name must be non None, to have no commit, it must
  have a branch. Like git, you cannot have head point to no commit without it
  pointing to a branch.
  '''

  commit_id: Optional[str] = None
  ''' the current dir is based off of this commit id, if any '''

  branch_name: Optional[str] = None
  ''' the current head is tied to this branch. new commits move the branch. '''

  def __post_init__(self):
    check_obj_types(self, dict(
      commit_id = optional_t(exact_t(str)),
      branch_name = optional_t(exact_t(str)),
    ))
    if (self.commit_id is None) == (self.branch_name is None):
      raise TypeError(head_ref_name + " must be a branch name or a commit id")

class RitError(Exception):
  '''
  an error raised by rit

  how to render:
    error_msg = exc.msg % exc.args
    logger.error(exc.msg, *exc.args)
  '''

  def __init__(self, msg, *args):
    super(RitError, self).__init__()
    self.msg = msg
    self.args = args

@dataclass
class RitResource:
  '''
  a resource to query the rit directory and cache results

  All interactions with the rit directory should go through this object.

  Any external changes to the rit directory invalidate's this object's cache and
  in that case, _clear should be called. However, no user of this resource
  should be calling _clear. Instead this class' api should be extended and that
  new method should call _clear.

  TODO: ensure all mutations of the rit directory are through this object, e.g.,
  tar creation / deletion.
  '''

  root_rit_dir: str
  ''' the root rit directory '''

  prevent_mutations: bool = False
  '''
  Set to True to prevent setter functions. Setting this to True makes it safe to
  give to consumers of this api. It prevents them from changing the rit dir
  directly.
  '''

  _paths: RitPaths = None
  ''' cache for paths property '''

  _head: HeadNode = None
  ''' cache for head property '''

  _commits: dict[str, Commit] = field(default_factory=dict)
  ''' cache for get_commit '''

  _branches: dict[str, Branch] = field(default_factory=dict)
  ''' cache for get_branch '''

  _branch_name_to_commit_ids: dict[str, str] = None
  ''' cache for get_branch_name_to_commit_ids '''

  _commit_id_to_branch_names: dict[str, list[str]] = None
  ''' cache for get_commit_id_to_branch_names '''

  _branch_names: list[str] = None
  ''' cache for get_branch_names '''

  _commit_ids: list[str] = None
  ''' cache for get_commit_ids '''

  _short_commit_tree: dict[str, list[str]] = None
  ''' cache for get_commit_tree '''

  def __post_init__(self) -> None:
    check_obj_types(self, dict(
      root_rit_dir = exact_t(str),
    ))

  def initialize(self):
    '''
    creates the rit directory

    if already initialized, raise RitError
    '''
    try:
      paths = RitPaths.build_rit_paths(self.root_rit_dir, init=True)
      logger.info("Successfully created rit directory: %s", paths.rit_dir)
    except FileExistsError:
      raise RitError("The rit directory already exists: %s", self.paths.rit_dir)

  def _clear(self):
    ''' If the rit directory is modified, then the cache must be cleared '''
    cleared_rit = RitResource(self.root_rit_dir)
    self._head = cleared_rit._head
    self._commits = cleared_rit._commits
    self._branches = cleared_rit._branches
    self._branch_name_to_commit_ids = cleared_rit._branch_name_to_commit_ids
    self._commit_id_to_branch_names = cleared_rit._commit_id_to_branch_names
    self._branch_names = cleared_rit._branch_names
    self._commit_ids = cleared_rit._commit_ids
    self._short_commit_tree = cleared_rit._short_commit_tree

  ''' SET '''

  def add_commit(self, commit: Commit):
    ''' add the commit to the rit dir '''
    if self.prevent_mutations:
      raise RitError("Doing this would mutate the rit directory, and that is disabled for this RitResource")
    self._write_commit(commit)
    self._clear()

  def set_branch(self, branch: Branch):
    ''' add the branch to the rit dir '''
    if self.prevent_mutations:
      raise RitError("Doing this would mutate the rit directory, and that is disabled for this RitResource")
    self._write_branch(branch)
    self._clear()

  def set_head(self, head: HeadNode):
    ''' set the new head point '''
    if self.prevent_mutations:
      raise RitError("Doing this would mutate the rit directory, and that is disabled for this RitResource")
    self._write_head(head)
    self._clear()

  ''' GET '''

  @property
  def paths(self):
    ''' returns a RitPaths object for this rit directory '''
    if self._paths is None:
      self._paths = self._read_paths()
    return self._paths

  @property
  def head(self):
    ''' returns the HeadNode object for this rit directory '''
    if self._head is None:
      self._head = self._read_head()
    return self._head

  def get_head_commit_id(self):
    ''' get the commit id of the head, None if there isn't one '''
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
    ''' get all commit ids '''
    if self._commit_ids is None:
      self._commit_ids = self._read_commit_ids()
    return self._commit_ids

  def get_commit(self, commit_id: str, *, ensure=False):
    '''
    get commit object of a commit id

    return a commit if found

    otherwise return None, if ensure is set to True, the raise instead of return None.
    '''
    if commit_id not in self._commits:
      try:
        self._commits[commit_id] = self._read_commit(commit_id)
      except FileNotFoundError:
        if ensure:
          raise RitError("Unable to load expected commit")
        return None
    return self._commits[commit_id]

  def is_commit(self, commit_id: str):
    ''' return True if commit_id has a commit '''
    return self.get_commit(commit_id) is not None

  def get_branch_names(self):
    ''' return names of all branches '''
    if self._branch_names is None:
      self._branch_names = self._read_branch_names()
    return self._branch_names

  def get_branch(self, name: str, *, ensure=False):
    '''
    query for branch by name

    returns None if not found. raises RitError instead if ensure is True
    '''
    if name not in self._branches:
      try:
        self._branches[name] = self._read_branch(name)
      except FileNotFoundError:
        if ensure:
          raise RitError("Unable to load expected branch")
        return None
    return self._branches[name]

  def is_branch(self, name: str):
    ''' return True if the branch name has a branch '''
    return self.get_branch(name) is not None

  def get_branch_name_to_commit_ids(self):
    ''' see _populate_commit_to_branch_map '''
    if self._branch_name_to_commit_ids is None:
      self._populate_commit_to_branch_map()
    return self._branch_name_to_commit_ids

  def get_commit_id_to_branch_names(self):
    ''' see _populate_commit_to_branch_map '''
    if self._commit_id_to_branch_names is None:
      self._populate_commit_to_branch_map()
    return self._commit_id_to_branch_names

  def get_commit_tree(self):
    '''
    returns a map of shortened commit prefixes to a list of all commit ids with
    that prefix

    the tree is used to find full commit ids given partial ones.
    '''
    if self._short_commit_tree is None:
      self._short_commit_tree = defaultdict(list)
      for commit_id in self.get_commit_ids():
        self._short_commit_tree[commit_id[:short_hash_index]].append(commit_id)
    return self._short_commit_tree

  ''' helpers '''

  def _populate_commit_to_branch_map(self):
    '''
    populate the commit <-> branch maps

    branches include the HEAD node

    if a branch doesn't have a commit, the commit and branch will not have
    entries in the maps
    '''
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

  ''' IO '''

  def _read_paths(self):
    root_rit_dir = os.path.realpath(self.root_rit_dir)
    rit_dir = os.path.join(root_rit_dir, rit_dir_name)
    last_root_rit_dir = None
    while not os.path.isdir(rit_dir):
      last_root_rit_dir = root_rit_dir
      root_rit_dir = os.path.dirname(root_rit_dir)
      if last_root_rit_dir == root_rit_dir:
        raise RitError("Unable to locate rit directory")
      rit_dir = os.path.join(root_rit_dir, rit_dir_name)
    return RitPaths.build_rit_paths(root_rit_dir)

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

def get_tar_path(rit: RitResource, commit_id: str):
  ''' get a commit's tar path, where the backup for that commit is '''
  return os.path.join(rit.paths.backups, commit_id + '.tar')

def get_snar_path(rit: RitResource, commit_id: str):
  ''' get a commit's star path, where the backup's metadata for that commit is '''
  return os.path.join(rit.paths.backups, commit_id + '.snar')


''' COMMIT HELPERS '''

def hash_commit(create_time: float, msg: str, snar: str, tar: str):
  ''' create a commit_id from '''
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
  ''' verify tar is the correct version and GNU '''
  logger.debug("Checking tar version")
  process = subprocess.Popen(['tar', '--version'], stdout=subprocess.PIPE)
  contents = process.stdout.read()
  process.wait()
  version = contents.decode('utf-8').split('\n', 1)[0]
  logger.debug("Tar Version: %s", version)
  assert 'GNU tar' in version, "You must have a GNU tar installed"

def status_tar(rit: RitResource, verbose: bool):
  ''' returns True if rit directory is dirty '''
  parent_commit_id = rit.get_head_commit_id()
  work_snar = os.path.join(rit.paths.work, 'ref.snar')
  if parent_commit_id is not None:
    head_snar = get_snar_path(rit, parent_commit_id)
    # TODO: move into rit resource
    shutil.copyfile(head_snar, work_snar)

  check_tar()
  tar_cmd = ['tar', '-cvg', work_snar, f'--exclude={rit_dir_name}', '-f', os.devnull, '.']
  logger.debug("Running tar command: %s", tar_cmd)

  # TODO: move into rit resource
  process = subprocess.Popen(tar_cmd, cwd=rit.paths.root, stdout=subprocess.PIPE)
  terminated = False
  dirty = False
  while True:
    line = process.stdout.readline()
    if not line:
      break

    if line == b'./\n':
      continue

    dirty = True
    if verbose:
      output = line.decode('utf-8').strip()
      logger.info("\t- %s", colorize(fg + red, output))
    else:
      terminated = True
      try:
        process.terminate()
      except Exception:
        pass
      break

  # still need to read the stdout to prevent blocking and therefore deadlock
  if terminated:
    while process.stdout.read(DEFAULT_BUFFER_SIZE):
      pass

  exit_code = process.wait()
  if not terminated and exit_code != 0:
    raise RitError("Creating commit's tar failed with exit code: %d", exit_code)

  os.remove(work_snar)
  return dirty

def create_commit(rit: RitResource, create_time: float, msg: str):
  ''' create a commit with the current head as the parent commit (if any) '''
  head = rit.head
  parent_commit_id = rit.get_head_commit_id()
  logger.debug("Parent ref: %s", parent_commit_id)

  work_tar = os.path.join(rit.paths.work, 'ref.tar')
  logger.debug("Working tar: %s", work_tar)

  work_snar = os.path.join(rit.paths.work, 'ref.snar')
  logger.debug("Working snar: %s", work_snar)

  if parent_commit_id is not None:
    head_snar = get_snar_path(rit, parent_commit_id)
    logger.debug("Copying previous snar: %s", head_snar)
    # TODO: move into rit resource
    shutil.copyfile(head_snar, work_snar)
  else:
    logger.debug("Using fresh snar file since no parent commit")

  check_tar()
  opts = '-cz'
  if logger.getEffectiveLevel() <= logging.DEBUG:
    opts += 'v'
  opts += 'g'
  tar_cmd = ['tar', opts, work_snar, f'--exclude={rit_dir_name}', '-f', work_tar, '.']
  logger.debug("Running tar command: %s", tar_cmd)
  # TODO: move into rit resource
  process = subprocess.Popen(tar_cmd, cwd=rit.paths.root)
  # TODO: doesn't forward SIGTERM, only SIGINT
  exit_code = process.wait()
  if exit_code != 0:
    raise RitError("Creating commit's tar failed with exit code: %d", exit_code)

  commit_id = hash_commit(create_time, msg, work_snar, work_tar)

  logger.debug("Moving working snar into backups directory")
  snar = get_snar_path(rit, commit_id)
  os.rename(work_snar, snar)

  logger.debug("Moving working tar into backups directory")
  tar = get_tar_path(rit, commit_id)
  os.rename(work_tar, tar)

  commit = Commit(parent_commit_id, commit_id, create_time, msg)
  rit.add_commit(commit)
  if rit.head.commit_id is not None:
    new_head = HeadNode(commit_id=commit_id, branch_name=None)
    rit.set_head(new_head)
  else:
    rit.set_branch(Branch(rit.head.branch_name, commit_id))
  return commit


''' RESET HELPERS '''

def apply_commit(rit: RitResource, commit: Commit):
  '''
  apply the commit to the rit directory

  If the current rit directory isn't clean and isn't the parent of the commit
  being applied, the results will not be the contents of commit.

  See restore_to_commit.
  '''
  logger.info("Applying commit: %s", commit.commit_id)
  tar_file = get_tar_path(rit, commit.commit_id)
  tar_cmd = ['tar', '-xg', os.devnull, '-f', tar_file]
  # rit resource thing?
  process = subprocess.Popen(tar_cmd, cwd=rit.paths.root)
  exit_code = process.wait()
  if exit_code != 0:
    raise RitError("Failed while trying to apply commit: %s", commit.commit_id)

def restore_to_commit(rit: RitResource, commit: Commit):
  '''
  This gets the chain of commits from commit to root and applies them. If there
  are changes in the working directory relative to current head, then those will
  be destroyed.


  '''
  logger.debug('resetting to %s', commit.commit_id)

  commit_chain = [commit]
  while commit.parent_commit_id is not None:
    commit = rit.get_commit(commit.parent_commit_id, ensure=True)
    commit_chain.append(commit)
  commit_chain.reverse()

  for commit in commit_chain:
    apply_commit(rit, commit)

''' BRANCH HELPERS '''

@dataclass
class ResolvedRef:
  '''
  the user provides a ref, which can reference head, a branch or commit. this
  object contains the HeadNode, Branch and Commit that the user's ref is
  referring to. all 3 or None can be defined.

  see resolve_ref
  '''

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
  if head is None
    if branch is None:
      ref doesn't refer to a branch
    else:
      ref points to this branch
  else:
    if branch is None:
      head points to a commit.
      head points to a branch with no commit.
    else:
      head points to this branch
  '''

  head: Optional[HeadNode] = None
  '''
  if head is None:
    ref was provided and not the head
  else:
    ref was omitted or explicitly set to the head
  '''

def resolve_commit(rit: RitResource, partial_commit_id: str):
  '''
  resolve a user provided commit id to a commit. if no commit is found, then
  return None. if the ref is an ambiguous shortened commit id, then this
  function raises an exception.
  '''
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

def resolve_ref(rit: RitResource, ref: Optional[str]):
  '''
  resolve a user provided reference

  if ref is None, then ref refers to the current head. ref can also explicitly
  refer to the current head. ref otherwise refers to a branch. if the branch is
  not found, then the ref refers to a commit. if no commit is found, all 3
  fields of ResolvedRef will be None.

  if the ref is an ambiguous shortened commit id, then this function raises an
  exception.

  see the def of ResolvedRef
  '''
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

def resolve_refs(rit: RitResource, refs: list[str], all: bool):
  '''
  Returns information regarding the provided refs
  '''
  resolved_refs: list[ResolvedRef] = []

  if not refs:
    refs.append(None)
  if all:
    refs.extend(rit.get_branch_names())
  for ref in refs:
    res = resolve_ref(rit, ref)
    resolved_refs.append(res)

  return resolved_refs

branch_name_re = re.compile('^\\w+$')
def validate_branch_name(name: str):
  ''' return whether this string is a valid branch name '''
  if name == head_ref_name:
    raise RitError("Branch can't be named the same as the head ref: %s", name)
  elif branch_name_re.search(name) is None:
    raise RitError("Invalid branch name: %s", name)

def _pprint_dur(dur: int, name: str):
  return f"{dur} {name}{'s' if dur > 1 else ''}"

def pprint_time_duration(start: float, end: float):
  ''' pretty print a time duration '''
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
    parts.append(_pprint_dur(int(dur_year), 'year'))
  elif dur_year >= 1:
    parts.append(_pprint_dur(int(dur_year), 'year'))
    parts.append(_pprint_dur(int(dur_month) % 12, 'month'))
  elif dur_month >= 1:
    parts.append(_pprint_dur(int(dur_month) % 12, 'month'))
  elif dur_day >= 1:
    parts.append(_pprint_dur(int(dur_day), 'day'))
  elif dur_hour >= 1:
    parts.append(_pprint_dur(int(dur_hour) % 60, 'hour'))
  elif dur_min >= 1:
    parts.append(_pprint_dur(int(dur_min) % 60, 'minute'))
  elif dur_sec >= 20:
    parts.append(_pprint_dur(int(dur_sec) % 60, 'second'))
  else:
    return 'Just now'
  return ', '.join(parts) + ' ago'


''' SUB LOG COMMANDS '''

def log_commits(rit: RitResource, commits: list[Commit]):
  '''
  Returns tuple of the following:
  - commit_graph: a tree containing all provided commits
  - leafs: the set of leaf notes of the tree
  - commit_id_to_commit: a map of each commit to a full Commit object
  - commit_id_to_branch_names: a map of each commit_id to branch names, including the head_ref_name
  '''
  leafs: set[str] = set()
  commit_graph: dict[str, str] = {}
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
  commit_id_to_commit: dict[str, Commit] = {}
  for commit_id in leafs:
    logger.info("Log branch from %s", commit_id[:short_hash_index])
    while commit_id is not None:
      if commit_id not in commit_id_to_commit:
        commit_id_to_commit[commit_id] = rit.get_commit(commit_id, ensure=True)
      commit = commit_id_to_commit[commit_id]

      colored_commit_id = colorize(fg + yellow, commit.commit_id[:short_hash_index])

      if commit.commit_id in commit_id_to_branch_names:
        branch_names = commit_id_to_branch_names[commit.commit_id]
        colored_branch_names = []
        for branch_name in branch_names:
          if branch_name == head_ref_name:
            colored_branch_names.append(colorize(fg + blue, branch_name))
          else:
            colored_branch_names.append(colorize(fg + green, branch_name))
        branch_details = f"({', '.join(colored_branch_names)}) "
      else:
        branch_details = ''

      time_duration = pprint_time_duration(commit.create_time, now)
      date_details = f'({time_duration}) '

      logger.info("* %s %s%s%s", colored_commit_id, date_details, branch_details, commit.msg)
      commit_id = commit_graph[commit_id]
  return commit_graph, leafs, commit_id_to_commit, commit_id_to_branch_names

''' SUB BRANCH COMMANDS '''

def delete_branch(rit: RitResource, name: str):
  ''' removes a branch '''
  try:
    os.remove(os.path.join(rit.paths.branches, name))
  except FileNotFoundError:
    raise RitError("Failed to remove branch since it didn't exist.")

def list_branches(rit: RitResource):
  ''' logs branches to logger '''
  head = rit.head
  head_branch_name = head.branch_name
  branch_names = rit.get_branch_names()
  for branch_name in branch_names:
    this_sym = '*' if branch_name == head_branch_name else ' '
    branch = rit.get_branch(branch_name, ensure=True)
    commit = rit.get_commit(branch.commit_id, ensure=True)
    colored_commit_id = colorize(fg + yellow, branch.commit_id[:short_hash_index])
    colored_branch_name = colorize(fg + green, branch_name)
    logger.info("%s %s\t%s %s", this_sym, colored_branch_name, colored_commit_id, commit.msg)
  return head, branch_names

def create_branch(rit: RitResource, name: str, ref: Optional[str], force: bool):
  '''
  creates a branch with name name at ref ref. if the branch already exists,
  force will move the branch to the new commit.
  '''
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
  return res

def log_refs(rit: RitResource, refs: list[str], all: bool, full: bool):
  '''
  Returns the commit tree containing the given refs. If none are given, assumes
  head. If all is true, appends refs.
  '''
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

  return log_commits(rit, commits)

def show_ref(rit: RitResource, ref: Optional[str]):
  ''' log the contents of a specific reference '''
  res = resolve_ref(rit, ref)
  if res.commit is None:
    if res.head is not None:
      raise RitError("head branch doesn't have any commits to show")
    else:
      raise RitError("Unable to locate ref: %s", ref)

  tar_file = get_tar_path(rit, res.commit.commit_id)
  tar_cmd = ['tar', '-tf', tar_file]
  process = subprocess.Popen(tar_cmd, stdout=subprocess.PIPE)
  changes = []
  while True:
    line = process.stdout.readline()
    if not line:
      break
    elif line == b'./\n':
      continue
    output = line.decode('utf-8').strip()
    changes.append(output)
    logger.info("\t- %s", colorize(fg + cyan, output))
  results = process.wait()
  if results != 0:
    raise RitError("tar command failed with exit code %d", results)
  return res, changes

def status_head(rit: RitResource):
  ''' run status_tar on HEAD with logging '''
  if rit.head.branch_name is not None:
    head_id = rit.head.branch_name
  else:
    head_id = rit.head.commit_id
  logger.info("%s -> %s", head_ref_name, head_id)
  if not status_tar(rit, True):
    logger.info("Clean working directory!")

'''
API

You should be able to do anything you want with these functions.
'''

def query(*, root_rit_dir: str):
  '''
  Return a read only RitResource used for querying the rit directory.

  CLI users get information via stdout. That's not helpful to for python users,
  so they instead get access to the full data structure.

  For advanced users who want write access to the rit directory, construct a
  RitResource directly with prevent_mutations set to False and read the class'
  docs.
  '''
  return RitResource(root_rit_dir, prevent_mutations=True)

def init(*, root_rit_dir: str):
  logger.debug("init")
  rit = RitResource(root_rit_dir)
  rit.initialize()

def commit(*, root_rit_dir, msg: str):
  logger.debug('commit')
  logger.debug('  msg: %s', msg)
  check_types(
    msg = (msg, exact_t(str)),
  )

  rit = RitResource(root_rit_dir)
  commit = create_commit(rit, time.time(), msg)
  logger.info("Created commit %s: %s", commit.commit_id[:short_hash_index], commit.msg)
  return commit

def reset(*, root_rit_dir: str, ref: str, hard: bool):
  '''
  A reset tries to move the head to ref. If head is a branch, it instead moves
  the branch. If head is a commit, it just moves head to the new commit. If it's
  a hard reset, then post moving head, the working changes are removed.

  Here, a non hard reset is effectively the same as git's reset with no
  arguments. In git, a reset with no args is --mixed, and since we don't have
  staged changes, --mixed and --soft are the same in this context.  For that
  reason, here, we just use the terminology reset instead of soft reset or mixed
  reset.
  '''
  logger.debug('reset')
  logger.debug('  ref: %s', ref)
  logger.debug('  hard: %s', hard)
  check_types(
    ref = (ref, exact_t(str)),
    hard = (hard, exact_t(bool)),
  )

  rit = RitResource(root_rit_dir)
  res = resolve_ref(rit, ref)

  if res.head is not None:
    raise RitError("Attempted to reset to head")
  elif res.commit is None:
    raise RitError("Unable to resolve ref to commit: %s", ref)
  commit = res.commit

  if res.branch is not None:
    new_head = HeadNode(branch_name = res.branch.name)
  else:
    new_head = HeadNode(commit_id = commit.commit_id)
  rit.set_head(new_head)

  if hard:
    restore_to_commit(rit, commit)

  logger.info("Successful reset. Commit this checkout to get a clean rit status.")
  return res

def checkout(*, root_rit_dir: str, ref: str, force: bool):
  '''
  Checkout ref (overwriting any changes if force is True).

  It will also check that the current working directory is clean so that we know
  no data is lost. If the working tree is dirty, then force needs to be set to
  True to forcibly delete these changes.

  Returns ref resolved, as a ResolvedRef.

  The end result is that head points to ref, and the working directory is
  restored to the point of ref.

  It is the equivalent of the following:
  - if head is a branch, set head to the underlying commit
  - hard reset to ref
  - set head to ref
  Or if you allow head to be moved to non equivalent commits:
  - set head to ref
  - hard reset to new head
  '''
  logger.debug('checkout')
  logger.debug('  ref: %s', ref)
  logger.debug('  force: %s', force)
  check_types(
    ref = (ref, exact_t(str)),
    force = (force, exact_t(bool)),
  )

  rit = RitResource(root_rit_dir)
  res = resolve_ref(rit, ref)
  if res.head is not None:
    raise RitError("Attempted to checkout head ref")
  elif res.commit is None:
    raise RitError("Unable to resolve ref to commit: %s", ref)
  commit = res.commit

  head_commit_id = rit.get_head_commit_id()
  if head_commit_id is not None and head_commit_id != commit.commit_id:
    if not force and status_tar(rit, False):
      raise RitError("Uncommitted changes! Commit them or use -f to destroy them.")
    restore_to_commit(rit, commit)

  if res.branch is not None:
    new_head = HeadNode(branch_name = res.branch.name)
  else:
    new_head = HeadNode(commit_id = commit.commit_id)
  rit.set_head(new_head)

  logger.info("Successful checkout. Commit this checkout to get a clean rit status.")
  return res

def branch(*, root_rit_dir: str, name: Optional[str], ref: Optional[str], force: bool, delete: bool):
  '''
  ref is a ref name or commit id or head_ref_name

  If creating a branch, returns ref resolved, as ResolvedRef.
  If listing all branches, returns (current_branch_name: str, all_branch_names: list[str])
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

  rit = RitResource(root_rit_dir)

  if name is not None:
    validate_branch_name(name)

  if delete:
    if force:
      raise RitError("You can't force delete branches")
    elif name is None:
      raise RitError("You must specify a branch to delete")
    elif ref is not None:
      raise RitError("You can't specify a reference branch with the delete option")

    delete_branch(rit, name)

  elif name is None:
    if force:
      raise RitError("You cannot specify force while listing branches")
    elif ref is not None:
      raise RitError("You cannot specify a ref branch while listing branches")

    return list_branches(rit)

  else:
    return create_branch(rit, name, ref, force)

def log(*, root_rit_dir: str, refs: list[str], all: bool, full: bool):
  logger.debug('log')
  logger.debug('  refs: %s', refs)
  logger.debug('  all: %s', all)
  logger.debug('  full: %s', all)
  check_types(
    refs = (refs, list_t(exact_t(str))),
    all = (all, exact_t(bool)),
    full = (full, exact_t(bool)),
  )

  rit = RitResource(root_rit_dir)
  return log_refs(rit, refs, all, full)

def show(*, root_rit_dir: str, ref: Optional[str]):
  logger.debug('show')
  logger.debug('  ref: %s', ref)
  check_types(ref = (ref, optional_t(exact_t(str))))

  rit = RitResource(root_rit_dir)
  return show_ref(rit, ref)

def status(*, root_rit_dir: str):
  logger.debug('status')

  rit = RitResource(root_rit_dir)
  status_head(rit)

def reflog(*, root_rit_dir: str):
  logger.debug('reflog')

  rit = RitResource(root_rit_dir)
  raise NotImplementedError()

def prune(*, root_rit_dir: str):
  # Prune lost branches
  logger.debug('prune')

  rit = RitResource(root_rit_dir)
  raise NotImplementedError()

''' ARG HANDLERS '''

def init_main(argv, prog):
  parser = argparse.ArgumentParser(description="Initialize a raw backup directory", prog=prog)
  args = parser.parse_args(argv)
  init(root_rit_dir=os.getcwd(), **vars(args))

def commit_main(argv, prog):
  parser = argparse.ArgumentParser(description="Create a commit from the current state", prog=prog)
  parser.add_argument('msg', help="The commit msg")
  args = parser.parse_args(argv)
  commit(root_rit_dir=os.getcwd(), **vars(args))

def checkout_main(argv, prog):
  parser = argparse.ArgumentParser(description="Log the current commit history", prog=prog)
  parser.add_argument('ref', help="The ref to checkout")
  parser.add_argument('-f', '--force', action='store_true', help="If there are uncommitted changes, automatically remove them.")
  args = parser.parse_args(argv)
  checkout(root_rit_dir=os.getcwd(), **vars(args))

def branch_main(argv, prog):
  parser = argparse.ArgumentParser(description="Create a new branch", prog=prog)
  parser.add_argument('name', nargs='?', help="The name of the branch to create. If omitted, lists all branches.")
  parser.add_argument('ref', nargs='?', help="The head of the new branch. By default, the current commit is used.")
  parser.add_argument('-f', '--force', action='store_true', help="The head of the new branch. By default, the current commit is used.")
  parser.add_argument('-d', '--delete', action='store_true', help="Delete the specified branch.")
  args = parser.parse_args(argv)
  branch(root_rit_dir=os.getcwd(), **vars(args))

def show_main(argv, prog):
  parser = argparse.ArgumentParser(description="Show contents of a commit", prog=prog)
  parser.add_argument('ref', nargs='?', help="The ref to show commit contents of. By default, head.")
  args = parser.parse_args(argv)
  show(root_rit_dir=os.getcwd(), **vars(args))

def status_main(argv, prog):
  parser = argparse.ArgumentParser(description="Show the current directory's diff state.", prog=prog)
  args = parser.parse_args(argv)
  status(root_rit_dir=os.getcwd(), **vars(args))

def log_main(argv, prog):
  parser = argparse.ArgumentParser(description="Log the current commit history", prog=prog)
  parser.add_argument('refs', nargs='*', help="The refs to log. By default, the current head is used.")
  parser.add_argument('--all', action='store_true', help="Include all branches")
  parser.add_argument('--full', action='store_true', help="Include more log data")
  args = parser.parse_args(argv)
  log(root_rit_dir=os.getcwd(), **vars(args))

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
    command_handlers[args.command](sub_argv, prog=f'{parser.prog} {args.command}')
    return 0
  except RitError as exc:
    logger.error(exc.msg, *exc.args)
    return 1

if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))
