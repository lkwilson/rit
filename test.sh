#!/usr/bin/env bash

bad() {
  set +x
  echo "Test failed!"
  exit 1
}

set -e

cd "$(dirname "$(realpath "$BASH_SOURCE")")"
rm -rf rit_test_dir
mkdir rit_test_dir
cd rit_test_dir



set -x
nosetests
python rit.py "$@" init || bad
python rit.py "$@" init && bad
python rit.py "$@" branch first && bad
python rit.py "$@" commit "Hey there" || bad
python rit.py "$@" branch first || bad
python rit.py "$@" branch 'invalid name' && bad
python rit.py "$@" branch 'invalid!name' && bad
python rit.py "$@" branch 'valid_name' || bad
python rit.py "$@" branch ' invalid_name' && bad
python rit.py "$@" branch 'invalid_name ' && bad
python rit.py "$@" branch 'invalid-name' && bad
python rit.py "$@" branch || bad
python rit.py "$@" commit "Oh hey there" || bad
python rit.py "$@" branch || bad
python rit.py "$@" branch new || bad
python rit.py "$@" branch || bad
python rit.py "$@" commit "move main" || bad
python rit.py "$@" branch || bad
python rit.py "$@" branch new main && bad
python rit.py "$@" branch || bad
python rit.py "$@" branch new main -f || bad
python rit.py "$@" branch || bad
python rit.py "$@" branch -d new main && bad
python rit.py "$@" branch -d -f && bad
python rit.py "$@" branch -d new -f && bad
python rit.py "$@" branch -d && bad
python rit.py "$@" branch || bad
python rit.py "$@" branch -d new || bad
python rit.py "$@" branch || bad
python rit.py "$@" branch -d new && bad
python rit.py "$@" log || bad
python rit.py "$@" log --all || bad
python rit.py "$@" checkout && bad
python rit.py "$@" checkout first || bad
python rit.py "$@" log || bad
python rit.py "$@" log main || bad
python rit.py "$@" log --all || bad
python rit.py "$@" checkout main || bad
python rit.py "$@" log || bad

set +x

echo "Success!"
exit 0
