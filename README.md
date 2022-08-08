# rit

Raw Git: a backup system that feels like git.

`rit` wraps tar's incremental backup feature with a python CLI and API.

It is space efficient and fast.

# CLI

## Getting Started

### Install
The rit script is standalone. Add it to your path, name it whatever you want, and run it:

```
rit --help
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

## checkout vs reset

### `checkout`
This will move what head points to (a branch or commit). If the target ref has a
different commit than the current head, it will attempt to reset the directory
to that point. If this destroys changes, then `--force` is required.

### `reset`
If head is a branch, it will move branch to point to target ref. It can also
reset the directory to the target commit with a `--force` flag.

## All CLI Help Outputs
```
$ rit  --help
usage: rit_lib.py [--verbose] [--quiet] {init,commit,checkout,reset,branch,show,status,log,prune}
rit_lib.py: error: the following arguments are required: command
```

## `rit init`
```
$ rit init --help
usage: rit_lib.py init [-h]

Initialize a raw backup directory

optional arguments:
  -h, --help  show this help message and exit
```

## `rit commit`
```
$ rit commit --help
usage: rit_lib.py commit [-h] msg

Create a commit from the current state

positional arguments:
  msg         The commit msg

optional arguments:
  -h, --help  show this help message and exit
```

## `rit checkout`
```
$ rit checkout --help
usage: rit_lib.py checkout [-h] [-f] ref

Log the current commit history

positional arguments:
  ref          The ref to checkout

optional arguments:
  -h, --help   show this help message and exit
  -f, --force  If there are uncommitted changes, automatically remove them.
```

## `rit reset`
```
usage: rit_lib.py reset [-h] [--hard] [ref]

Log the current commit history

positional arguments:
  ref         The ref to reset head to

optional arguments:
  -h, --help  show this help message and exit
  --hard      Apply the target commits upon reset
```

## `rit branch`
```
$ rit branch --help
usage: rit_lib.py branch [-h] [-f] [-d] [name] [ref]

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
$ rit show --help
usage: rit_lib.py show [-h] [ref]

Show contents of a commit

positional arguments:
  ref         The ref to show commit contents of. By default, head.

optional arguments:
  -h, --help  show this help message and exit
```

## `rit status`
```
$ rit status --help
usage: rit_lib.py status [-h]

Show the current directory's diff state.

optional arguments:
  -h, --help  show this help message and exit
```

## `rit log`
```
$ rit log --help
usage: rit_lib.py log [-h] [--all] [--full] [refs ...]

Log the current commit history

positional arguments:
  refs        The refs to log. By default, the current head is used.

optional arguments:
  -h, --help  show this help message and exit
  --all       Include all branches
  --full      Include more log data
```

## `rit prune`
```
$ rit prune --help
usage: rit_lib.py prune [-h]

Prune commits not part of a branch or head

optional arguments:
  -h, --help  show this help message and exit
```

# Python API

```py
def query_cmd(*, root_rit_dir: str): pass
def init_cmd(*, root_rit_dir: str): pass
def commit_cmd(*, root_rit_dir: str, msg: str): pass
def reset_cmd(*, root_rit_dir: str, ref: Optional[str], hard: bool): pass
def checkout_cmd(*, root_rit_dir: str, orphan: bool, ref_or_name: str, force: Optional[bool]): pass
def branch_cmd(*, root_rit_dir: str, name: Optional[str], ref: Optional[str], force: bool, delete: bool): pass
def log_cmd(*, root_rit_dir: str, refs: list[str], all: bool, full: bool): pass
def show_cmd(*, root_rit_dir: str, ref: Optional[str]): pass
def status_cmd(*, root_rit_dir: str): pass
def reflog_cmd(*, root_rit_dir: str): pass
def prune_cmd(*, root_rit_dir: str): pass
```

# Differences
As a result of being a subset of git:
- No concept of staged / indexed changes.
- Soft and mixed resetting are the same thing here.
Some deviations are made since we don't have the same limitations as git.
- You can forcibly move a branch that head points to.
- commit doesn't use `-m` flag: `commit "My commit message"` instead of `commit -m "My commit message"`

# Development
Contributions welcome!
## How to test
- You can import `rit_lib.py` and use the python api.
- You can run `rit_lib.py` directly. 
- You can run the helper script in bin.
- You can add bin to your PATH, and run `rit`.

## TODO
- You can't sigterm rit or it may leave stray tar processes lying around. We
  currently rely on signal forwarding to the process group, which only works for
  ctrl C / SIGINT
- Make it asyncio based (which also conveniently solves the previous item)
- `rit branch` with no commits doesn't warn me of anything
- `rit log --full` doesn't do anything

### Nice to haves:
- No `checkout -b`
- Require `checkout -m` to match git api
