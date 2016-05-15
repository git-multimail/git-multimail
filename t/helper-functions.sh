# some common useful shell functions

# portable echo that never does backslash processing
pecho() { printf %s\\n "$*"; }

# logging
log() { pecho "$@"; }
debug() { : log "DEBUG: $@" >&2; }
error() { log "ERROR: $@" >&2; }

# error handling
fatal() {
    error "$@";
    if test "$(command -v cleanup)" = cleanup
    then
	cleanup
    fi
    exit 1;
}
try() { "$@" || fatal "'$@' failed"; }

if [ -z "$SHARNESS_TEST_DIRECTORY" ]
then
    fatal "Please, source sharness.sh before helper-functions.sh"
fi

ZEROS=0000000000000000000000000000000000000000

if [ -z "$PYTHON" ]
then
    PYTHON=python
fi

if "$PYTHON" --version 2>&1 | grep -q "^Python 3"
then
    PYTHON_VERSION=3
    if command -v test_set_prereq >/dev/null
    then
	test_set_prereq PYTHON3
    fi
else
    PYTHON_VERSION=2
    if command -v test_set_prereq >/dev/null
    then
	test_set_prereq PYTHON2
    fi
fi

# Calling git-multimail
MULTIMAIL="$SHARNESS_TEST_DIRECTORY/../git-multimail/git_multimail.py"
MULTIMAIL_VERSION_QUOTED=$("$MULTIMAIL" --version |
    sed -e 's/^git-multimail version //' -e 's@[/\\]@\\\0@g')
export MULTIMAIL_VERSION_QUOTED
POST_RECEIVE="$SHARNESS_TEST_DIRECTORY/../git-multimail/post-receive.example"


test_email() {
    REFNAME="$1"
    OLDREV="$2"
    NEWREV="$3"
    shift 3
    pecho "$OLDREV" "$NEWREV" "$REFNAME" | USER=pushuser "$PYTHON" "$MULTIMAIL" "$@" >output
    RETCODE=$?
    cat output
    return $RETCODE
}

test_create() {
    REFNAME="$1"
    NEWREV=$(git rev-parse "$REFNAME")
    shift
    test_email "$REFNAME" "$ZEROS" "$NEWREV" "$@"
}

test_update() {
    REFNAME="$1"
    OLDREV=$(git rev-parse "$2")
    NEWREV=$(git rev-parse "$REFNAME")
    shift 2
    test_email "$REFNAME" "$OLDREV" "$NEWREV" "$@"
}

test_delete() {
    REFNAME="$1"
    OLDREV=$(git rev-parse "$REFNAME")
    shift
    git update-ref -d "$REFNAME" "$OLDREV" &&
    test_email "$REFNAME" "$OLDREV" "$ZEROS" "$@"
    RETCODE=$?
    git update-ref "$REFNAME" "$OLDREV" ||
        error "Error replacing reference $REFNAME to $OLDREV"
    return $RETCODE
}

test_rewind() {
    REFNAME="$1"
    OLDREV=$(git rev-parse "$REFNAME")
    NEWREV=$(git rev-parse "$2")
    shift 2
    git update-ref "$REFNAME" "$NEWREV" "$OLDREV" &&
    test_email "$REFNAME" "$OLDREV" "$NEWREV" "$@"
    RETCODE=$?
    git update-ref "$REFNAME" "$OLDREV" ||
        error "Error replacing reference $REFNAME to $OLDREV"
    return $RETCODE
}

# Like test_update, but using example post-receive script:
test_hook() {
    REFNAME="$1"
    OLDREV=$(git rev-parse "$2")
    NEWREV=$(git rev-parse "$REFNAME")
    shift 2
    pecho "$OLDREV" "$NEWREV" "$REFNAME" | USER=pushuser "$PYTHON" "$POST_RECEIVE" "$@" >output
    RETCODE=$?
    cat output
    return $RETCODE
}

save_git_config() {
    cp .git/config .git/config.bak &&
    test_when_finished 'cp .git/config.bak .git/config'
}

verbose_do() {
    if test $# -gt 1
    then
	(
	    printf "\$ %s" "$1"
	    shift
	    # Show each argument quoted (e.g. to distinguish between
	    # '' and nothing at all).
	    printf " '%s'" "$@"
	    printf '\n'
	)
    else
	printf "\$ %s\n" "$*"
    fi
    "$@"
}

# Default configuration
HOME="$SHARNESS_TEST_DIRECTORY"
XDG_CONFIG_HOME="$SHARNESS_TEST_DIRECTORY"
GIT_CONFIG_NOSYSTEM=1
export HOME XDG_CONFIG_HOME GIT_CONFIG_NOSYSTEM
GIT_AUTHOR_DATE="100000000 +0200"
GIT_COMMITTER_DATE="100000010 +0200"
export GIT_AUTHOR_DATE GIT_COMMITTER_DATE
# GIT_WORK_TREE and GIT_DIR must really be unset for the testsuite to
# be runnable from Git hooks (like pre-push). Others are less
# important, but let's remain on the safe side.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_INDEX_VERSION \
    GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_NAMESPACE
