import time
from dataclasses import dataclass
from typing import Callable, Optional

import rit_lib


''' types and ctors '''

@dataclass
class BackupType:
  name: str
  ''' the name of the backup class. This is prefixed to all branches. '''

  max_level_ages: list[float]
  ''' the max age for each level. 0 if it never expires. '''

  get_level_names: Callable[[float], list[str]]
  ''' a function that maps the current time into a set of levels '''

def get_periodic_backup_type():
  second = 1
  minute = 60 * second
  hour = 60 * minute
  day = 24 * hour
  # week = 7 * day
  year = 365.25 * day
  month = year / 12

  def get_level_names(now: float):
    '''
    return now split into level names. The full level name is the previous
    elements prepended and separated by an underscore.

    - The first level is a full backup.
    - If subsequent levels don't exist, they are built off the level before them.
    - If the last level exists already, then the backup is appended to the commit
      chain.

    Thus, this function must return at least 2 levels.
    '''
    # year, month, day, hour, 15 minute mark, exact minute
    return ['2022_05', '02', '12', '15']

  level_max_ages = [0, year, 3*month, month]

  return BackupType('periodic', level_max_ages, get_level_names)

''' api '''

def create_backup(rit_dir: str):
  backup_type = get_periodic_backup_type()
  backup_time = time.time()
  level_names = backup_type.get_level_names(backup_time)
  if len(level_names) < 2:
    raise rit_lib.RitError("Not enough levels we need at least 2")
  branch_names: list[str] = []
  previous_level_name = ''
  for level, level_name in enumerate(level_names):
    if previous_level_name:
      full_level_name = f"{previous_level_name}_{level_name}"
    else:
      full_level_name = level_name
    branch_names.push(f"{backup_type.name}_{level}_{full_level_name}")
    previous_level_name = full_level_name
  branch_names.reverse()

  rit_res = rit_lib.query_cmd(root_rit_dir=rit_dir)
  base_branch: Optional[rit_lib.Branch] = None
  while branch_names:
    branch_name = branch_names.pop()
    branch = rit_res.get_branch(branch_name)
    if branch is not None:
      base_branch = branch
    else:
      break

  if base_branch is None:
    rit_lib.checkout_cmd(root_rit_dir=rit_dir, orphan=True, ref_or_name=branch_name, force=None)
    rit_lib.commit_cmd(root_rit_dir=rit_dir, msg="Full standard backup")
  elif branch is None:
    rit_lib.branch_cmd(root_rit_dir=rit_dir, name=branch_name, ref=None, force=True, delete=False)
    rit_lib.checkout_cmd(root_rit_dir=rit_dir, orphan=False, ref_or_name=branch_name, force=False)
    rit_lib.reset_cmd(root_rit_dir=rit_dir, ref=base_branch.name, hard=False)
    rit_lib.commit_cmd(root_rit_dir=rit_dir, msg="Partial backup")
  else:
    if rit_res.head.branch_name is not None:
      branch = rit_res.get_branch(rit_res.head.branch_name)
      if branch is not None:
        rit_lib.checkout_cmd(root_rit_dir=rit_dir, orphan=False, ref_or_name=branch.commit_id, force=False)
    rit_lib.reset_cmd(root_rit_dir=rit_dir, ref=branch_name, hard=False)
    rit_lib.checkout_cmd(root_rit_dir=rit_dir, orphan=False, ref_or_name=branch_name, force=False)
    rit_lib.commit_cmd(root_rit_dir=rit_dir, msg="Extension backup")

  for branch_name in branch_names:
    rit_lib.branch_cmd(root_rit_dir=rit_dir, name=branch_name, ref=None, force=True, delete=False)

def prune_backup(backup_type: BackupType):
  pass
  # get all branches
  # get level expirations
  # filter backup_class
  # extract level
  # extract age
  # remove if expired
  # do commit prune

def restore_to_point(rit_dir: str, ref: Optional[str]):
  create_backup(rit_dir)
  rit = rit_lib.query_cmd(root_rit_dir=rit_dir)

  pass
  # create backup
  # find jump branches and increment
  # create jump branch
  # hard reset to ref
  # create new commit on jump branch
