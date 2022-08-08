import re
import time
from dataclasses import dataclass
from typing import Callable, Optional

import rit_lib


''' types and ctors '''

@dataclass
class BackupType:
  periodic_prefix: str
  '''
  the branch prefix of periodic backup points

  These are captured at whatever frequency requested. High frequency backups are
  pruned quicker, and low frequency backups are never pruned. Lowest frequency
  backups are full backups, not incremented.
  '''

  restore_prefix: str
  '''
  the branch prefix of backup points before and after restores

  For a restore, we create a new periodic backup and then create two branches
  for the jump point. One is the new periodic backup, where we restored from.
  The second is the restored location, where we restored to.

  The last n restore points are captured (n*2 branches). The top two commits of a restore
  prefix are before and after the restoration.
  '''

  manual_prefix: str
  '''
  the branch prefix of manually created backup points

  A manual backup point is created and labeled. These are never deleted.
  '''

  number_of_restore_points_to_save: int
  ''' the number of restore points to preserver before pruning '''

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

def create_backup(rit_dir: str, msg: str):
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
    branch_names.push(f"{backup_type.periodic_prefix}__lvl_{level}__{full_level_name}")
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
    backup_commit = rit_lib.commit_cmd(root_rit_dir=rit_dir, msg=msg)
  elif branch is None:
    rit_lib.branch_cmd(root_rit_dir=rit_dir, name=branch_name, ref=None, force=True, delete=False)
    rit_lib.checkout_cmd(root_rit_dir=rit_dir, orphan=False, ref_or_name=branch_name, force=False)
    rit_lib.reset_cmd(root_rit_dir=rit_dir, ref=base_branch.name, hard=False)
    backup_commit = rit_lib.commit_cmd(root_rit_dir=rit_dir, msg=msg)
  else:
    if rit_res.head.branch_name is not None:
      branch = rit_res.get_branch(rit_res.head.branch_name)
      if branch is not None:
        rit_lib.checkout_cmd(root_rit_dir=rit_dir, orphan=False, ref_or_name=branch.commit_id, force=False)
    rit_lib.reset_cmd(root_rit_dir=rit_dir, ref=branch_name, hard=False)
    rit_lib.checkout_cmd(root_rit_dir=rit_dir, orphan=False, ref_or_name=branch_name, force=False)
    backup_commit = rit_lib.commit_cmd(root_rit_dir=rit_dir, msg=msg)

  for branch_name in branch_names:
    rit_lib.branch_cmd(root_rit_dir=rit_dir, name=branch_name, ref=backup_commit.commit_id, force=True, delete=False)

  return backup_commit

def prune_backup(rit_dir: str):
  backup_type = get_periodic_backup_type()
  now = time.time()
  regex = re.compile(f'{backup_type.periodic_prefix}__level_(\\d+)__')
  rit_res = rit_lib.query_cmd(root_rit_dir=rit_dir)
  branch_names = rit_res.get_branch_names()
  pending_prune = []
  for branch_name in branch_names:
    match = regex.match(branch_name)
    if match is None:
      continue
    level = int(match.groups()[0])
    branch = rit_res.get_branch(branch_name)
    if branch is None:
      continue
    commit = rit_res.get_commit(branch.commit_id)
    if commit is None:
      continue
    age = now - commit.create_time
    max_age = backup_type.max_level_ages[level]
    if age > max_age:
      pending_prune.append(branch_name)

  for branch_name in pending_prune:
    rit_res = rit_lib.branch_cmd(root_rit_dir=rit_dir, name=branch_name, ref=None, force=False, delete=True)
  rit_lib.prune_cmd(root_rit_dir=rit_dir)

def restore_to_point(rit_dir: str, ref: Optional[str]):
  backup_type = get_periodic_backup_type()
  rit_res = rit_lib.query_cmd(root_rit_dir=rit_dir)
  res = rit_lib.resolve_ref(rit_res, ref)
  if res.commit is None:
    raise rit_lib.RitError("Unable to resolve restore point's commit")

  pre_restore_commit = create_backup(rit_dir, "Before restoration")
  rit_lib.checkout_cmd(root_rit_dir=rit_dir, orphan=False, ref_or_name=res.commit.commit_id, force=True)

  # build branch update map
  shift_updates = {
    f'{backup_type.restore_prefix}__idx_1__before': pre_restore_commit.commit_id,
    f'{backup_type.restore_prefix}__idx_1__after': res.commit.commit_id,
  }
  for idx in range(backup_type.number_of_restore_points_to_save-1, 0, -1):
    before_current_name = f'{backup_type.restore_prefix}__idx_{idx}__before'
    after_current_name = f'{backup_type.restore_prefix}__idx_{idx}__after'
    updated_index = idx + 1
    before_updated_name = f'{backup_type.restore_prefix}__idx_{updated_index}__before'
    after_updated_name = f'{backup_type.restore_prefix}__idx_{updated_index}__after'

    rit_res = rit_lib.query_cmd(root_rit_dir=rit_dir)
    before_current = rit_res.get_branch(before_current_name)
    if before_current is not None:
      shift_updates[before_updated_name] = before_current.commit_id
    after_current = rit_res.get_branch(after_current_name)
    if after_current is not None:
      shift_updates[after_updated_name] = after_current.commit_id

  for branch_name, branch_commit in shift_updates.items():
    rit_lib.branch_cmd(root_rit_dir=rit_dir, name=branch_name, ref=branch_commit, force=True, delete=False)
