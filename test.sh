#!/usr/bin/env bash

bad() {
  echo "Test failed!"
  exit 1
}

set -ex
rm -rf .rit
verbose=-v
python rit.py $verbose init || bad
python rit.py $verbose init && bad
python rit.py $verbose branch first && bad
python rit.py $verbose commit "Hey there" || bad
python rit.py $verbose branch first || bad
python rit.py $verbose branch || bad
python rit.py $verbose commit "Oh hey there" || bad
python rit.py $verbose branch || bad
python rit.py $verbose branch new || bad
python rit.py $verbose branch || bad
python rit.py $verbose commit "move main" || bad
python rit.py $verbose branch || bad
python rit.py $verbose branch new main && bad
python rit.py $verbose branch || bad
python rit.py $verbose branch new main -f || bad
python rit.py $verbose branch || bad
python rit.py $verbose branch -d new main && bad
python rit.py $verbose branch -d -f && bad
python rit.py $verbose branch -d new -f && bad
python rit.py $verbose branch -d && bad
python rit.py $verbose branch || bad
python rit.py $verbose branch -d new || bad
python rit.py $verbose branch -d new && bad
