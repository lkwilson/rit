#!/usr/bin/env bash

bad() {
  set +x
  echo "Test failed!"
  exit 1
}

set -e

rit_bin=../rit.py


cd "$(dirname "$(realpath "$BASH_SOURCE")")"

export TEST_ROOT_RIT_DIR=rit_test_dir
rm -rf "$TEST_ROOT_RIT_DIR"
mkdir "$TEST_ROOT_RIT_DIR"
nosetests

rm -rf "$TEST_ROOT_RIT_DIR"
mkdir "$TEST_ROOT_RIT_DIR"
cd "$TEST_ROOT_RIT_DIR"

set -x
python "$rit_bin" "$@" init || bad
python "$rit_bin" "$@" init && bad
python "$rit_bin" "$@" branch first && bad
touch a
python "$rit_bin" "$@" commit "Hey there" || bad
python "$rit_bin" "$@" branch first || bad
python "$rit_bin" "$@" branch 'invalid name' && bad
python "$rit_bin" "$@" branch 'invalid!name' && bad
python "$rit_bin" "$@" branch 'valid_name' || bad
python "$rit_bin" "$@" branch ' invalid_name' && bad
python "$rit_bin" "$@" branch 'invalid_name ' && bad
python "$rit_bin" "$@" branch 'invalid-name' && bad
python "$rit_bin" "$@" branch || bad
touch b
python "$rit_bin" "$@" commit "Oh hey there" || bad
python "$rit_bin" "$@" branch || bad
python "$rit_bin" "$@" branch new || bad
python "$rit_bin" "$@" branch || bad
touch c
python "$rit_bin" "$@" commit "move main" || bad
python "$rit_bin" "$@" branch || bad
python "$rit_bin" "$@" branch new main && bad
python "$rit_bin" "$@" branch || bad
python "$rit_bin" "$@" branch new main -f || bad
python "$rit_bin" "$@" branch || bad
python "$rit_bin" "$@" branch -d new main && bad
python "$rit_bin" "$@" branch -d -f && bad
python "$rit_bin" "$@" branch -d new -f && bad
python "$rit_bin" "$@" branch -d && bad
python "$rit_bin" "$@" branch || bad
python "$rit_bin" "$@" branch -d new || bad
python "$rit_bin" "$@" branch || bad
python "$rit_bin" "$@" branch -d new && bad
python "$rit_bin" "$@" log || bad
python "$rit_bin" "$@" log --all || bad
touch d
python "$rit_bin" "$@" checkout && bad
python "$rit_bin" "$@" checkout first && bad
python "$rit_bin" "$@" checkout first -f || bad
python "$rit_bin" "$@" log || bad
python "$rit_bin" "$@" log main || bad
python "$rit_bin" "$@" log --all || bad
python "$rit_bin" "$@" checkout main -f || bad
python "$rit_bin" "$@" log || bad
python "$rit_bin" "$@" show || bad
python "$rit_bin" "$@" status || bad
python "$rit_bin" "$@" commit "post checkout commit" || bad
python "$rit_bin" "$@" show || bad
python "$rit_bin" "$@" status || bad

python "$rit_bin" "$@" branch base || bad
python "$rit_bin" "$@" branch add_aa || bad
python "$rit_bin" "$@" checkout add_aa || bad
touch aa
python "$rit_bin" "$@" commit "add aa" || bad

python "$rit_bin" "$@" branch add_bb base || bad
python "$rit_bin" "$@" checkout add_bb -f || bad
[ -f aa ] && bad
touch bb
python "$rit_bin" "$@" commit "add bb" || bad
python "$rit_bin" "$@" checkout add_aa -f || bad
[ -f bb ] && bad
[ -f aa ] || bad
python "$rit_bin" "$@" checkout add_bb -f || bad
[ -f bb ] || bad
[ -f aa ] && bad
python "$rit_bin" "$@" checkout base -f || bad
[ -f bb ] && bad
[ -f aa ] && bad

# checkout --orphan
python "$rit_bin" "$@" checkout --orphan basic_reset || bad
python "$rit_bin" "$@" checkout basic_reset && bad
python "$rit_bin" "$@" commit "Reset to only have one commit" || bad
python "$rit_bin" "$@" checkout basic_reset || bad
touch ddd
python "$rit_bin" "$@" commit "Add ddd" || bad
python "$rit_bin" "$@" branch orph_bak || bad

python "$rit_bin" "$@" reset base || bad
[ -f ddd ] || bad
python "$rit_bin" "$@" checkout base || bad
[ -f ddd ] || bad
python "$rit_bin" "$@" checkout basic_reset || bad
[ -f ddd ] || bad
python "$rit_bin" "$@" checkout first && bad
[ -f ddd ] || bad
python "$rit_bin" "$@" checkout basic_reset || bad
[ -f ddd ] || bad
python "$rit_bin" "$@" reset orph_bak || bad
[ -f ddd ] || bad
python "$rit_bin" "$@" checkout basic_reset || bad
[ -f ddd ] || bad
python "$rit_bin" "$@" checkout orph_bak || bad
[ -f ddd ] || bad
python "$rit_bin" "$@" checkout first || bad
[ -f ddd ] && bad

# TODO: prune test

set +x

echo "All tests succeeded!"
exit 0
