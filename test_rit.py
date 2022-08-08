import os

# public api
from rit_lib import init_cmd, commit_cmd, reset_cmd, checkout_cmd, branch_cmd, log_cmd, show_cmd, status_cmd, prune_cmd, query_cmd
# advanced api
import rit_lib

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
    print(i, rit_lib.pprint_time_duration(0, i))
  # assert False

def touch(root_dir: str, fn: str):
  full_path = os.path.join(root_dir, fn)
  with open(full_path, 'a'):
    pass
  return full_path

def test_python_api():
  root_rit_dir = os.environ.get('TEST_ROOT_RIT_DIR')
  assert os.path.exists(root_rit_dir), "Can't find test rit dir"
  base_kwargs = dict(root_rit_dir=root_rit_dir)

  # can you init?
  assert init_cmd(**base_kwargs) is None

  # can you commit files?
  touch(root_rit_dir, 'first')
  first_commit = commit_cmd(**base_kwargs, msg="first")
  touch(root_rit_dir, 'second')
  second_commit = commit_cmd(**base_kwargs, msg="second")
  touch(root_rit_dir, 'third')
  third_commit = commit_cmd(**base_kwargs, msg="third")

  # can you checkout files?
  ref = checkout_cmd(**base_kwargs, orphan=False, ref_or_name=first_commit.commit_id, force=False)
  assert ref.commit.commit_id == first_commit.commit_id

  # dirty dir prevents checkout
  fourth_file = touch(root_rit_dir, 'fourth')
  try:
    checkout_cmd(**base_kwargs, orphan=False, ref_or_name=second_commit.commit_id, force=False)
    assert False
  except rit_lib.RitError:
    pass

  # force checkout ignores dirty dir
  ref = checkout_cmd(**base_kwargs, orphan=False, ref_or_name=third_commit.commit_id, force=True)
  curr_head = ref
  assert ref.commit.commit_id == third_commit.commit_id
  # file is gone, restore / checkout complete
  assert not os.path.exists(fourth_file)

  # can create branch at comits?
  ref = branch_cmd(**base_kwargs, name='first_b', ref=first_commit.commit_id, force=False, delete=False)
  assert ref.commit.commit_id == first_commit.commit_id
  ref = branch_cmd(**base_kwargs, name='second_b', ref=second_commit.commit_id, force=False, delete=False)
  assert ref.commit.commit_id == second_commit.commit_id
  ref = branch_cmd(**base_kwargs, name='third_b', ref=third_commit.commit_id, force=False, delete=False)
  assert ref.commit.commit_id == third_commit.commit_id
  # can create branch from branch
  ref = branch_cmd(**base_kwargs, name='third_b_copy', ref='third_b', force=False, delete=False)
  assert ref.commit.commit_id == third_commit.commit_id

  # can move branch without force?
  try:
    branch_cmd(**base_kwargs, name='second_b', ref=None, force=False, delete=False)
    assert False
  except rit_lib.RitError:
    pass

  # move branch with force
  ref = branch_cmd(**base_kwargs, name='second_b', ref=None, force=True, delete=False)
  assert ref.commit.commit_id == curr_head.commit.commit_id
  assert ref.commit.commit_id != second_commit.commit_id

  # delete branch
  ref = branch_cmd(**base_kwargs, name='second_b', ref=None, force=False, delete=True)
  assert ref is None

  # delete non existent branch
  try:
    branch_cmd(**base_kwargs, name='second_b', ref=None, force=False, delete=True)
    assert False
  except rit_lib.RitError:
    pass

  # create it again after delete
  ref = branch_cmd(**base_kwargs, name='second_b', ref=None, force=False, delete=False)
  assert ref.commit.commit_id == curr_head.commit.commit_id

  expected_all_branches = set(['main', 'first_b', 'second_b', 'third_b', 'third_b_copy'])
  branch_res = branch_cmd(**base_kwargs, name=None, ref=None, force=False, delete=False)
  assert isinstance(branch_res, tuple)
  head, all_branches = branch_res
  assert head.branch_name is None
  assert set(all_branches) == expected_all_branches

  checkout_cmd(**base_kwargs, orphan=False, ref_or_name='third_b', force=False)
  branch_res = branch_cmd(**base_kwargs, name=None, ref=None, force=False, delete=False)
  assert isinstance(branch_res, tuple)
  head, all_branches = branch_res
  assert head.branch_name == 'third_b'
  assert set(all_branches) == expected_all_branches

  ref, changes = show_cmd(**base_kwargs, ref='third_b')
  assert ref.branch.name == 'third_b'
  assert ref.commit.msg == 'third'
  assert './third' in changes

  ref, changes = show_cmd(**base_kwargs, ref='first_b')
  assert ref.branch.name == 'first_b'
  assert ref.commit.msg == 'first'
  assert './first' in changes

  assert status_cmd(**base_kwargs) is None

  checkout_cmd(**base_kwargs, orphan=False, ref_or_name=second_commit.commit_id, force=True)
  branch_res = branch_cmd(**base_kwargs, name='deviate', ref=None, force=False, delete=False)
  assert branch_res.commit.commit_id == second_commit.commit_id
  checkout_cmd(**base_kwargs, orphan=False, ref_or_name='deviate', force=False)
  deviate_commit = commit_cmd(**base_kwargs, msg="deviation")
  checkout_cmd(**base_kwargs, orphan=False, ref_or_name='third_b', force=False)

  branch_res = branch_cmd(**base_kwargs, name=None, ref=None, force=False, delete=False)
  assert isinstance(branch_res, tuple)
  head, all_branches = branch_res
  assert head.commit_id is None
  assert head.branch_name == 'third_b'

  commit_graph, leafs, commit_id_to_commit, commit_id_to_branch_names = log_cmd(**base_kwargs, refs=[], all=False, full=False)
  assert len(leafs) == 1
  leaf_commit_id = list(leafs)[0]
  assert head.branch_name in commit_id_to_branch_names[leaf_commit_id]
  head_commit_id = leaf_commit_id

  commit_graph, leafs, commit_id_to_commit, commit_id_to_branch_names = log_cmd(**base_kwargs, refs=['first_b'], all=False, full=False)
  assert len(leafs) == 1
  leaf_commit_id = list(leafs)[0]
  assert 'first_b' in commit_id_to_branch_names[leaf_commit_id]

  commit_graph, leafs, commit_id_to_commit, commit_id_to_branch_names = log_cmd(**base_kwargs, refs=[first_commit.commit_id], all=False, full=False)
  assert len(leafs) == 1
  leaf_commit_id = list(leafs)[0]
  assert 'first_b' in commit_id_to_branch_names[leaf_commit_id]

  commit_graph, leafs, commit_id_to_commit, commit_id_to_branch_names = log_cmd(**base_kwargs, refs=[third_commit.commit_id], all=False, full=False)
  assert len(leafs) == 1
  leaf_commit_id = list(leafs)[0]
  assert head.branch_name in commit_id_to_branch_names[leaf_commit_id]

  commit_graph, leafs, commit_id_to_commit, commit_id_to_branch_names = log_cmd(**base_kwargs, refs=[first_commit.commit_id, third_commit.commit_id], all=False, full=False)
  assert len(leafs) == 1
  leaf_commit_id = list(leafs)[0]
  assert head.branch_name in commit_id_to_branch_names[leaf_commit_id]

  commit_graph, leafs, commit_id_to_commit, commit_id_to_branch_names = log_cmd(**base_kwargs, refs=['first_b', 'second_b'], all=False, full=False)
  assert len(leafs) == 1
  leaf_commit_id = list(leafs)[0]
  assert 'second_b' in commit_id_to_branch_names[leaf_commit_id]

  deviate_commit_id = None
  commit_graph, leafs, commit_id_to_commit, commit_id_to_branch_names = log_cmd(**base_kwargs, refs=[], all=True, full=False)
  assert len(leafs) == 2
  for leaf in leafs:
    if leaf == head_commit_id:
      assert 'third_b' in commit_id_to_branch_names[leaf]
      assert rit_lib.head_ref_name in commit_id_to_branch_names[leaf]
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

  def info(root_rit_dir, refs, all):
    rit_res = query_cmd(root_rit_dir=root_rit_dir)
    resolved_refs = rit_lib.resolve_refs(rit_res, refs, all)
    commit_id_to_branch_names = rit_res.get_commit_id_to_branch_names()
    return resolved_refs, commit_id_to_branch_names

  refs, commit_id_to_branch_names = info(**base_kwargs, refs=[], all=False)
  assert len(refs) == 1
  assert refs[0].head is not None

  refs, commit_id_to_branch_names = info(**base_kwargs, refs=[rit_lib.head_ref_name], all=False)
  assert len(refs) == 1
  assert refs[0].head is not None

  refs, commit_id_to_branch_names = info(**base_kwargs, refs=[rit_lib.head_ref_name], all=True)
  assert len(refs) == 7
  assert refs[0].head is not None

  refs, commit_id_to_branch_names = info(**base_kwargs, refs=[], all=True)
  assert len(refs) == 7
  assert refs[0].head is not None

  refs, commit_id_to_branch_names = info(**base_kwargs, refs=['first_b'], all=True)
  assert len(refs) == 7
  assert refs[0].head is None
  assert refs[0].branch.name == 'first_b'
  assert refs[0].commit.commit_id == first_commit.commit_id

  refs, commit_id_to_branch_names = info(**base_kwargs, refs=['first_b', 'third_b'], all=True)
  assert len(refs) == 8
  assert refs[0].head is None
  assert refs[0].branch.name == 'first_b'
  assert refs[0].commit.commit_id == first_commit.commit_id
  assert refs[1].head is None
  assert refs[1].branch.name == 'third_b'
  assert refs[1].commit.commit_id == third_commit.commit_id

  for ref in refs:
    if ref.branch is not None:
      assert ref.commit.commit_id in commit_id_to_branch_names
    else:
      assert ref.commit.commit_id not in commit_id_to_branch_names

  refs, commit_id_to_branch_names = info(**base_kwargs, refs=['first_b'], all=False)
  assert len(refs) == 1
  assert refs[0].head is None
  assert refs[0].branch.name == 'first_b'
  assert refs[0].commit.commit_id == first_commit.commit_id

  # assert that delete can't be set when orphaning
  try:
    checkout_cmd(**base_kwargs, orphan=True, ref_or_name='o_test', force=True)
    assert False
  except TypeError:
    pass

  try:
    checkout_cmd(**base_kwargs, orphan=True, ref_or_name='o_test', force=False)
    assert False
  except TypeError:
    pass

  try:
    checkout_cmd(**base_kwargs, orphan=True, ref_or_name=None, force=None)
    assert False
  except TypeError:
    pass

  checkout_cmd(**base_kwargs, orphan=True, ref_or_name='otest', force=None)

  rit_res = query_cmd(**base_kwargs)
  assert rit_res.head.branch_name == 'otest'
  assert rit_res.head.commit_id is None
  assert rit_res.get_branch('otest') is None

  new_commit = commit_cmd(**base_kwargs, msg='Initial commit for otest')

  # Verify no parents
  assert new_commit.parent_commit_id is None

  # get rit res
  rit_res = query_cmd(**base_kwargs)

  # verify commit id matches what was returned
  new_commit_lookup = rit_res.get_commit(new_commit.commit_id, ensure=True)
  assert new_commit_lookup.commit_id is not None
  assert new_commit_lookup.commit_id == new_commit.commit_id
  assert new_commit_lookup.parent_commit_id == new_commit.parent_commit_id
  assert new_commit_lookup.create_time == new_commit.create_time
  assert new_commit_lookup.msg == new_commit.msg
  root_commit_id = new_commit_lookup.commit_id

  # verify that head is still on branch
  assert rit_res.head.branch_name == 'otest'
  assert rit_res.head.commit_id is None

  # verify that branch matches claimed commit
  new_branch = rit_res.get_branch('otest')
  assert new_branch is not None
  assert new_branch.commit_id == new_commit.commit_id

  # add files
  branch_cmd(**base_kwargs, name="otest_root", ref=None, force=False, delete=False)
  otest_a_file = touch(root_rit_dir, 'otest_a')
  commit_cmd(**base_kwargs, msg="add a")
  branch_cmd(**base_kwargs, name="otest_a", ref=None, force=False, delete=False)
  otest_b_file = touch(root_rit_dir, 'otest_b')
  top_commit = commit_cmd(**base_kwargs, msg="add b")
  branch_cmd(**base_kwargs, name="otest_b", ref=None, force=False, delete=False)
  otest_c_file = touch(root_rit_dir, 'otest_c')

  rit_res = query_cmd(**base_kwargs)
  assert rit_res.head.branch_name == 'otest'
  otest_root_branch = rit_res.get_branch('otest_root')
  assert otest_root_branch is not None
  otest_a_branch = rit_res.get_branch('otest_a')
  assert otest_a_branch is not None
  otest_b_branch = rit_res.get_branch('otest_b')
  assert otest_b_branch is not None
  otest_branch = rit_res.get_branch('otest')
  assert otest_branch is not None
  assert otest_branch.commit_id == otest_b_branch.commit_id
  assert top_commit.commit_id == otest_branch.commit_id

  assert top_commit.parent_commit_id == otest_a_branch.commit_id
  assert root_commit_id == rit_res.get_commit(otest_a_branch.commit_id, ensure=True).parent_commit_id

  commit_chain = [root_commit_id, top_commit.parent_commit_id, top_commit.commit_id]

  # make orphan and make sure changes are still there
  checkout_cmd(**base_kwargs, orphan=True, ref_or_name='otest_2', force=None)

  assert os.path.exists(otest_a_file)
  assert os.path.exists(otest_b_file)
  assert os.path.exists(otest_c_file)

  checkout_cmd(**base_kwargs, orphan=True, ref_or_name='otest_3', force=None)

  assert os.path.exists(otest_a_file)
  assert os.path.exists(otest_b_file)
  assert os.path.exists(otest_c_file)

  # get rit res
  rit_res = query_cmd(**base_kwargs)
  assert rit_res.get_branch('otest_2') is None
  assert rit_res.get_branch('otest_3') is None
  assert rit_res.head.branch_name == 'otest_3'

  reset_cmd(**base_kwargs, ref=commit_chain[0], hard=False)
  rit_res = query_cmd(**base_kwargs)
  assert rit_res.head.branch_name == 'otest_3'
  assert rit_res.head.commit_id is None
  this_branch = rit_res.get_branch('otest_3', ensure=True)
  assert this_branch is not None
  assert this_branch.commit_id == commit_chain[0]
  assert os.path.exists(otest_a_file)
  assert os.path.exists(otest_b_file)
  assert os.path.exists(otest_c_file)

  reset_cmd(**base_kwargs, ref=None, hard=False)
  rit_res = query_cmd(**base_kwargs)
  assert rit_res.get_branch('otest_2') is None
  assert rit_res.head.branch_name == 'otest_3'

  reset_cmd(**base_kwargs, ref=rit_lib.head_ref_name, hard=False)
  rit_res = query_cmd(**base_kwargs)
  assert rit_res.get_branch('otest_2') is None
  assert rit_res.head.branch_name == 'otest_3'

  reset_cmd(**base_kwargs, ref=commit_chain[1], hard=False)
  rit_res = query_cmd(**base_kwargs)
  assert rit_res.head.branch_name == 'otest_3'
  assert rit_res.head.commit_id is None
  this_branch = rit_res.get_branch('otest_3', ensure=True)
  assert this_branch is not None
  assert this_branch.commit_id == commit_chain[1]
  assert os.path.exists(otest_a_file)
  assert os.path.exists(otest_b_file)
  assert os.path.exists(otest_c_file)

  reset_cmd(**base_kwargs, ref=None, hard=False)
  rit_res = query_cmd(**base_kwargs)
  assert rit_res.head.branch_name == 'otest_3'

  reset_cmd(**base_kwargs, ref=rit_lib.head_ref_name, hard=False)
  rit_res = query_cmd(**base_kwargs)
  assert rit_res.head.branch_name == 'otest_3'

  reset_cmd(**base_kwargs, ref=commit_chain[2], hard=False)
  rit_res = query_cmd(**base_kwargs)
  assert rit_res.head.branch_name == 'otest_3'
  assert rit_res.head.commit_id is None
  this_branch = rit_res.get_branch('otest_3', ensure=True)
  assert this_branch is not None
  assert this_branch.commit_id == commit_chain[2]
  assert os.path.exists(otest_a_file)
  assert os.path.exists(otest_b_file)
  assert os.path.exists(otest_c_file)

  checkout_cmd(**base_kwargs, orphan=False, ref_or_name=commit_chain[2], force=False)
  rit_res = query_cmd(**base_kwargs)
  assert rit_res.head.branch_name is None
  assert rit_res.head.commit_id == commit_chain[2]
  reset_cmd(**base_kwargs, ref=commit_chain[0], hard=False)
  rit_res = query_cmd(**base_kwargs)
  assert rit_res.head.branch_name is None
  assert rit_res.head.commit_id == commit_chain[0]
  assert os.path.exists(otest_a_file)
  assert os.path.exists(otest_b_file)
  assert os.path.exists(otest_c_file)

  reset_cmd(**base_kwargs, ref=None, hard=False)
  rit_res = query_cmd(**base_kwargs)
  assert rit_res.head.commit_id == commit_chain[0]

  reset_cmd(**base_kwargs, ref=rit_lib.head_ref_name, hard=False)
  rit_res = query_cmd(**base_kwargs)
  assert rit_res.head.commit_id == commit_chain[0]

  reset_cmd(**base_kwargs, ref=commit_chain[2], hard=False)
  rit_res = query_cmd(**base_kwargs)
  assert rit_res.head.branch_name is None
  assert rit_res.head.commit_id == commit_chain[2]
  assert os.path.exists(otest_a_file)
  assert os.path.exists(otest_b_file)
  assert os.path.exists(otest_c_file)

  reset_cmd(**base_kwargs, ref=commit_chain[0], hard=False)
  rit_res = query_cmd(**base_kwargs)
  assert rit_res.head.branch_name is None
  assert rit_res.head.commit_id == commit_chain[0]
  assert os.path.exists(otest_a_file)
  assert os.path.exists(otest_b_file)
  assert os.path.exists(otest_c_file)

  reset_cmd(**base_kwargs, ref=commit_chain[2], hard=True)
  rit_res = query_cmd(**base_kwargs)
  assert rit_res.head.branch_name is None
  assert rit_res.head.commit_id == commit_chain[2]
  assert os.path.exists(otest_a_file)
  assert os.path.exists(otest_b_file)
  assert not os.path.exists(otest_c_file)

  reset_cmd(**base_kwargs, ref=commit_chain[1], hard=True)
  rit_res = query_cmd(**base_kwargs)
  assert rit_res.head.branch_name is None
  assert rit_res.head.commit_id == commit_chain[1]
  assert os.path.exists(otest_a_file)
  assert not os.path.exists(otest_b_file)
  assert not os.path.exists(otest_c_file)

  reset_cmd(**base_kwargs, ref=commit_chain[0], hard=True)
  rit_res = query_cmd(**base_kwargs)
  assert rit_res.head.branch_name is None
  assert rit_res.head.commit_id == commit_chain[0]
  assert not os.path.exists(otest_a_file)
  assert not os.path.exists(otest_b_file)
  assert not os.path.exists(otest_c_file)

  reset_cmd(**base_kwargs, ref=commit_chain[1], hard=True)
  rit_res = query_cmd(**base_kwargs)
  assert rit_res.head.branch_name is None
  assert rit_res.head.commit_id == commit_chain[1]
  assert os.path.exists(otest_a_file)
  assert not os.path.exists(otest_b_file)
  assert not os.path.exists(otest_c_file)

  reset_cmd(**base_kwargs, ref=commit_chain[2], hard=True)
  rit_res = query_cmd(**base_kwargs)
  assert rit_res.head.branch_name is None
  assert rit_res.head.commit_id == commit_chain[2]
  assert os.path.exists(otest_a_file)
  assert os.path.exists(otest_b_file)
  assert not os.path.exists(otest_c_file)

  checkout_cmd(**base_kwargs, orphan=False, ref_or_name='otest_3', force=True)
  reset_cmd(**base_kwargs, ref=commit_chain[2], hard=True)
  rit_res = query_cmd(**base_kwargs)
  assert rit_res.head.branch_name == 'otest_3'
  assert rit_res.head.commit_id is None
  assert os.path.exists(otest_a_file)
  assert os.path.exists(otest_b_file)
  assert not os.path.exists(otest_c_file)

  reset_cmd(**base_kwargs, ref=commit_chain[1], hard=True)
  rit_res = query_cmd(**base_kwargs)
  assert rit_res.head.branch_name == 'otest_3'
  assert rit_res.head.commit_id is None
  assert os.path.exists(otest_a_file)
  assert not os.path.exists(otest_b_file)
  assert not os.path.exists(otest_c_file)

  reset_cmd(**base_kwargs, ref=commit_chain[0], hard=True)
  rit_res = query_cmd(**base_kwargs)
  assert rit_res.head.branch_name == 'otest_3'
  assert rit_res.head.commit_id is None
  assert not os.path.exists(otest_a_file)
  assert not os.path.exists(otest_b_file)
  assert not os.path.exists(otest_c_file)

  checkout_cmd(**base_kwargs, orphan=False, ref_or_name='deviate', force=True)
  rit_res = query_cmd(**base_kwargs)
  head_branch = rit_res.get_branch(rit_res.head.branch_name)
  head_commit_id = head_branch.commit_id
  head_commit = rit_res.get_commit(head_commit_id, ensure=True)
  reset_cmd(**base_kwargs, ref=head_commit.parent_commit_id, hard=False)
  rit_res = query_cmd(**base_kwargs)
  rit_res.get_commit(head_commit_id, ensure=True)
  prune_res = prune_cmd(**base_kwargs)
  rit_res = query_cmd(**base_kwargs)
  assert rit_res.get_commit(head_commit_id) is None
  assert len(prune_res) == 1
  assert prune_res[0] == head_commit_id

  rit_res = query_cmd(**base_kwargs)
  head_commit = rit_res.get_head_commit_id()
  checkout_cmd(**base_kwargs, orphan=False, ref_or_name=head_commit, force=True)
  reset_cmd(**base_kwargs, ref='deviate', hard=False)
  rit_res = query_cmd(**base_kwargs)
  assert rit_res.head.branch_name is None
  assert rit_res.head.commit_id == head_commit
