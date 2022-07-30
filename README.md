# rit

Raw Git: a backup system that feels like git.

`rit` wraps tar's incremental backup feature with a python CLI and API.

It is space efficient and fast.

# CLI

## Getting Started

### Install
The rit script is standalone. Add it to your path, name it whatever you want, and run it:

```
python rit.py --help
```

### Convert directory to a rit directory
```
$ rit init
I: Successfully created rit directory: /data/.rit
```

Files and directories within the rit directory are being tracked by rit. The
default branch is main. Note that no backups have been made yet.

### Create a backup
```
$ rit commit "Initial commit"
```

### See backup history
```
$ rit log
I: Log branch from 872093e
I: * 872093e (Just now) (main, HEAD) More time
I: * 4397a9f (Just now) Make change
I: * 6db5029 (35 seconds ago) (before_change) following
I: * 2958b82 (39 seconds ago) next
I: * 85a5c51 (42 seconds ago) Initial commit
```

### See all branches
```
$ rit branch
I:   before_change      6db5029 following
I: * main       872093e More time
```

### See changes from last backup
```
$ rit status
I: HEAD -> before_change
I: Clean working directory!
$ touch a
$ rit status
I: HEAD -> before_change
I:      - ./a
```

### Revert to previous branch
```
$ rit checkout 6ba2d45
I: Applying commit: 85a5c51f1fa57a64af8cc631694dfaf32b8f4557
I: Applying commit: 2958b8233be62399bf21b8877c762a373e66aba6
I: Applying commit: 6db502975012df355ab72e6cc4511fd80cce3afa
I: Applying commit: 1fce29658835df20551059042dc5dcd426411968
I: Applying commit: 6ba2d454c5c36b61359dbcfc6bdd898861bf1bb6
I: Successful checkout. Commit this checkout to get a clean rit status.
$ rit status
I: HEAD -> 6ba2d454c5c36b61359dbcfc6bdd898861bf1bb6
I:      - ./a
```

Note: When checking out branches, it breaks tar's diff ability due to metadata.
Therefore, after a checkout, you can assume the diff is clean, but you will need
to create a new "restore point" commit to cleanup the status.

```
$ rit commit "Restore to point"
I: Created commit f8bb898: Restore to point
$ rit status
I: HEAD -> f8bb8981108091ea784f7e25668994e737833efb
I: Clean working directory!
```

### See all backup histories
```
$ rit log --all
I: Log branch from 1fce296
I: * 1fce296 (Just now) (before_change, HEAD) Take a different path
I: * 6db5029 (4 minutes ago) following
I: * 2958b82 (4 minutes ago) next
I: * 85a5c51 (4 minutes ago) Initial commit
I: Log branch from 872093e
I: * 872093e (4 minutes ago) (main) More time
I: * 4397a9f (4 minutes ago) Make change
I: * 6db5029 (4 minutes ago) following
I: * 2958b82 (4 minutes ago) next
I: * 85a5c51 (4 minutes ago) Initial commit
```

### See current backup's changes
```
$ rit show
I:      - ./b
```

## All CLI Help Outputs
```
$ python rit.py  --help
usage: rit.py [--verbose] [--quiet] {init,commit,checkout,branch,show,status,log}
rit.py: error: the following arguments are required: command
```

## `rit init`
```
$ python rit.py init --help
usage: rit.py init [-h]

Initialize a raw backup directory

optional arguments:
  -h, --help  show this help message and exit
```

## `rit commit`
```
$ python rit.py commit --help
usage: rit.py commit [-h] msg

Create a commit from the current state

positional arguments:
  msg         The commit msg

optional arguments:
  -h, --help  show this help message and exit
```

## `rit checkout`
```
$ python rit.py checkout --help
usage: rit.py checkout [-h] [-f] ref

Log the current commit history

positional arguments:
  ref          The ref to checkout

optional arguments:
  -h, --help   show this help message and exit
  -f, --force  If there are uncommitted changes, automatically remove them.
```

## `rit branch`
```
$ python rit.py branch --help
usage: rit.py branch [-h] [-f] [-d] [name] [ref]

Create a new branch

positional arguments:
  name          The name of the branch to create. If omitted, lists all branches.
  ref           The head of the new branch. By default, the current commit is used.

optional arguments:
  -h, --help    show this help message and exit
  -f, --force   The head of the new branch. By default, the current commit is used.
  -d, --delete  Delete the specified branch.
```

## `rit show``
```
$ python rit.py show --help
usage: rit.py show [-h] [ref]

Show contents of a commit

positional arguments:
  ref         The ref to show commit contents of. By default, head.

optional arguments:
  -h, --help  show this help message and exit
```

## `rit status`
```
$ python rit.py status --help
usage: rit.py status [-h]

Show the current directory's diff state.

optional arguments:
  -h, --help  show this help message and exit
```

## `rit log`
```
$ python rit.py log --help
usage: rit.py log [-h] [--all] [--full] [refs ...]

Log the current commit history

positional arguments:
  refs        The refs to log. By default, the current head is used.

optional arguments:
  -h, --help  show this help message and exit
  --all       Include all branches
  --full      Include more log data
```

# Python API

```py
def init(): pass
def commit(*, msg: str): pass
def checkout(*, ref: str, force: bool): pass
def branch(*, name: Optional[str], ref: Optional[str], force: bool, delete: bool): pass
def log(*, refs: list[str], all: bool, full: bool): pass
def show(*, ref: Optional[str]): pass
def status(): pass
# def reflog(): pass
# def prune(): pass
# def reroot(): pass
```

# TODO

- You can't sigterm rit or it may leave stray tar processes lying around.
- No pruning of untracked commits, those that are not part of a branch tree.
- No squashing of historical commits
- Only stores a single full backup which can be risky
- No `checkout -b`
- `rit branch` with no commits doesn't warn me of anything
- `rit log --full` doesn't do anything
- See NotImplementedError's at the bottom of rit.py
