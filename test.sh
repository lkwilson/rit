#!/usr/bin/env bash

bad() {
  set +x
  echo "Test failed!"
  exit 1
}

set -e

rit_bin=../rit.py

cd "$(dirname "$(realpath "$BASH_SOURCE")")"
rm -rf rit_test_dir
mkdir rit_test_dir
cd rit_test_dir



set -x
nosetests
python "$rit_bin" "$@" init || bad
python "$rit_bin" "$@" init && bad
python "$rit_bin" "$@" branch first && bad
python "$rit_bin" "$@" commit "Hey there" || bad
touch a
python "$rit_bin" "$@" branch first || bad
python "$rit_bin" "$@" branch 'invalid name' && bad
python "$rit_bin" "$@" branch 'invalid!name' && bad
python "$rit_bin" "$@" branch 'valid_name' || bad
python "$rit_bin" "$@" branch ' invalid_name' && bad
python "$rit_bin" "$@" branch 'invalid_name ' && bad
python "$rit_bin" "$@" branch 'invalid-name' && bad
python "$rit_bin" "$@" branch || bad
python "$rit_bin" "$@" commit "Oh hey there" || bad
touch b
python "$rit_bin" "$@" branch || bad
python "$rit_bin" "$@" branch new || bad
python "$rit_bin" "$@" branch || bad
python "$rit_bin" "$@" commit "move main" || bad
touch c
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
python "$rit_bin" "$@" checkout && bad
python "$rit_bin" "$@" checkout first || bad
python "$rit_bin" "$@" log || bad
python "$rit_bin" "$@" log main || bad
python "$rit_bin" "$@" log --all || bad
python "$rit_bin" "$@" checkout main || bad
python "$rit_bin" "$@" log || bad

set +x

echo "Success!"
exit 0
