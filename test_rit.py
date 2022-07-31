import os
import rit

# public api
from rit import init, commit, checkout, branch, log, show, status, reflog, prune

def test_pprint_time_duration():
  min = 60
  hour = 60 * min
  day = 24 * hour
  month = 32 * day  # overestimate
  year = 370 * day  # overestimate
  for i in [
    .5,
    .9,
    1,
    1.5,
    3,
    30,
    min,
    2 * min,
    hour,
    3 * hour,
    day,
    2 * day,
    month,
    2 * month,
    year,
    2 * year,
    3 * year,
    10 * year,
    100 * year,
  ]:
    print(i, rit.pprint_time_duration(0, i))
  # assert False

def touch(fn: str):
  with open(fn, 'a'):
    pass

def test_python_api():
  root_rit_dir = os.environ.get('TEST_ROOT_RIT_DIR')
  assert os.path.exists(root_rit_dir), "Can't find test rit dir"
  base_kwargs = dict(root_rit_dir=root_rit_dir)

  # can you init?
  assert init(**base_kwargs) is None

  # not implemented stuff
  try:
    reflog(**base_kwargs)
    assert False
  except NotImplementedError:
    pass

  try:
    prune(**base_kwargs)
    assert False
  except NotImplementedError:
    pass

  # can you commit files?
  touch(os.path.join(root_rit_dir, 'first'))
  first_commit = commit(**base_kwargs, msg="first")
  touch(os.path.join(root_rit_dir, 'second'))
  second_commit = commit(**base_kwargs, msg="second")
  touch(os.path.join(root_rit_dir, 'third'))
  third_commit = commit(**base_kwargs, msg="third")

  # can you checkout files?
  ref = checkout(**base_kwargs, ref=first_commit.commit_id, force=False)
  assert ref.commit.commit_id == first_commit.commit_id

  # dirty dir prevents checkout
  fourth_file = os.path.join(root_rit_dir, 'fourth')
  touch(fourth_file)
  try:
    checkout(**base_kwargs, ref=second_commit.commit_id, force=False)
    assert False
  except rit.RitError:
    pass

  # force checkout ignores dirty dir
  ref = checkout(**base_kwargs, ref=third_commit.commit_id, force=True)
  curr_head = ref
  assert ref.commit.commit_id == third_commit.commit_id
  # file is gone, restore / checkout complete
  assert not os.path.exists(fourth_file)

  # can create branch at comits?
  ref = branch(**base_kwargs, name='first_b', ref=first_commit.commit_id, force=False, delete=False)
  assert ref.commit.commit_id == first_commit.commit_id
  ref = branch(**base_kwargs, name='second_b', ref=second_commit.commit_id, force=False, delete=False)
  assert ref.commit.commit_id == second_commit.commit_id
  ref = branch(**base_kwargs, name='third_b', ref=third_commit.commit_id, force=False, delete=False)
  assert ref.commit.commit_id == third_commit.commit_id
  # can create branch from branch
  ref = branch(**base_kwargs, name='third_b_copy', ref='third_b', force=False, delete=False)
  assert ref.commit.commit_id == third_commit.commit_id

  # can move branch without force?
  try:
    branch(**base_kwargs, name='second_b', ref=None, force=False, delete=False)
    assert False
  except rit.RitError:
    pass

  # move branch with force
  ref = branch(**base_kwargs, name='second_b', ref=None, force=True, delete=False)
  assert ref.commit.commit_id == curr_head.commit.commit_id
  assert ref.commit.commit_id != second_commit.commit_id

  # delete branch
  ref = branch(**base_kwargs, name='second_b', ref=None, force=False, delete=True)
  assert ref is None

  # delete non existent branch
  try:
    branch(**base_kwargs, name='second_b', ref=None, force=False, delete=True)
    assert False
  except rit.RitError:
    pass

  # create it again after delete
  ref = branch(**base_kwargs, name='second_b', ref=None, force=False, delete=False)
  assert ref.commit.commit_id == curr_head.commit.commit_id

  expected_all_branches = set(['main', 'first_b', 'second_b', 'third_b', 'third_b_copy'])
  branch_res = branch(**base_kwargs, name=None, ref=None, force=False, delete=False)
  assert isinstance(branch_res, tuple)
  head, all_branches = branch_res
  assert head.branch_name is None
  assert set(all_branches) == expected_all_branches

  checkout(**base_kwargs, ref='third_b', force=False)
  branch_res = branch(**base_kwargs, name=None, ref=None, force=False, delete=False)
  assert isinstance(branch_res, tuple)
  head, all_branches = branch_res
  assert head.branch_name == 'third_b'
  assert set(all_branches) == expected_all_branches

  ref, changes = show(**base_kwargs, ref='third_b')
  assert ref.branch.name == 'third_b'
  assert ref.commit.msg == 'third'
  assert './third' in changes

  ref, changes = show(**base_kwargs, ref='first_b')
  assert ref.branch.name == 'first_b'
  assert ref.commit.msg == 'first'
  assert './first' in changes

  assert status(**base_kwargs) is None

  checkout(**base_kwargs, ref=second_commit.commit_id, force=True)
  branch_res = branch(**base_kwargs, name='deviate', ref=None, force=False, delete=False)
  assert branch_res.commit.commit_id == second_commit.commit_id
  checkout(**base_kwargs, ref='deviate', force=False)
  deviate_commit = commit(**base_kwargs, msg="deviation")
  checkout(**base_kwargs, ref='third_b', force=False)

  branch_res = branch(**base_kwargs, name=None, ref=None, force=False, delete=False)
  assert isinstance(branch_res, tuple)
  head, all_branches = branch_res
  assert head.commit_id is None
  assert head.branch_name == 'third_b'

  commit_graph, leafs, commit_id_to_commit, commit_id_to_branch_names = log(**base_kwargs, refs=[], all=False, full=False)
  assert len(leafs) == 1
  leaf_commit_id = list(leafs)[0]
  assert head.branch_name in commit_id_to_branch_names[leaf_commit_id]
  head_commit_id = leaf_commit_id

  commit_graph, leafs, commit_id_to_commit, commit_id_to_branch_names = log(**base_kwargs, refs=['first_b'], all=False, full=False)
  assert len(leafs) == 1
  leaf_commit_id = list(leafs)[0]
  assert 'first_b' in commit_id_to_branch_names[leaf_commit_id]

  commit_graph, leafs, commit_id_to_commit, commit_id_to_branch_names = log(**base_kwargs, refs=[first_commit.commit_id], all=False, full=False)
  assert len(leafs) == 1
  leaf_commit_id = list(leafs)[0]
  assert 'first_b' in commit_id_to_branch_names[leaf_commit_id]

  commit_graph, leafs, commit_id_to_commit, commit_id_to_branch_names = log(**base_kwargs, refs=[third_commit.commit_id], all=False, full=False)
  assert len(leafs) == 1
  leaf_commit_id = list(leafs)[0]
  assert head.branch_name in commit_id_to_branch_names[leaf_commit_id]

  commit_graph, leafs, commit_id_to_commit, commit_id_to_branch_names = log(**base_kwargs, refs=[first_commit.commit_id, third_commit.commit_id], all=False, full=False)
  assert len(leafs) == 1
  leaf_commit_id = list(leafs)[0]
  assert head.branch_name in commit_id_to_branch_names[leaf_commit_id]

  commit_graph, leafs, commit_id_to_commit, commit_id_to_branch_names = log(**base_kwargs, refs=['first_b', 'second_b'], all=False, full=False)
  assert len(leafs) == 1
  leaf_commit_id = list(leafs)[0]
  assert 'second_b' in commit_id_to_branch_names[leaf_commit_id]

  deviate_commit_id = None
  commit_graph, leafs, commit_id_to_commit, commit_id_to_branch_names = log(**base_kwargs, refs=[], all=True, full=False)
  assert len(leafs) == 2
  for leaf in leafs:
    if leaf == head_commit_id:
      assert 'third_b' in commit_id_to_branch_names[leaf]
      assert rit.head_ref_name in commit_id_to_branch_names[leaf]
    else:
      assert 'deviate' in commit_id_to_branch_names[leaf]
      deviate_commit_id = leaf
  assert deviate_commit_id == deviate_commit.commit_id

  assert commit_graph[deviate_commit_id] == second_commit.commit_id
  assert commit_graph[second_commit.commit_id] == first_commit.commit_id
  assert commit_graph[first_commit.commit_id] is None
  assert commit_graph[head_commit_id] == second_commit.commit_id
  assert deviate_commit_id in commit_id_to_commit
  assert head_commit_id in commit_id_to_commit
