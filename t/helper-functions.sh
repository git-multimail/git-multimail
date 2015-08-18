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
    PYTHON=python2
fi

# Calling git-multimail
if "$PYTHON" --version 2>&1 | grep -q "^Python 3"
then
    (cd "$SHARNESS_TEST_DIRECTORY/../git-multimail/" && make git_multimail3.py) >/dev/null 2>&1
    MULTIMAIL="$SHARNESS_TEST_DIRECTORY/../git-multimail/git_multimail3.py"
    if command -v test_set_prereq >/dev/null
    then
	test_set_prereq PYTHON3
    fi
else
    MULTIMAIL="$SHARNESS_TEST_DIRECTORY/../git-multimail/git_multimail.py"
    if command -v test_set_prereq >/dev/null
    then
	test_set_prereq PYTHON2
    fi
fi
MULTIMAIL_VERSION_QUOTED=$("$MULTIMAIL" --version |
    sed -e 's/^git-multimail version //' -e 's@[/\\]@\\\0@g')
POST_RECEIVE="$SHARNESS_TEST_DIRECTORY/../git-multimail/post-receive.example"


test_email() {
    REFNAME="$1"
    OLDREV="$2"
    NEWREV="$3"
    shift 3
    pecho "$OLDREV" "$NEWREV" "$REFNAME" | USER=pushuser "$MULTIMAIL" "$@" >output
    status=$?
    cat output
    return $status
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
    pecho "$OLDREV" "$NEWREV" "$REFNAME" | USER=pushuser "$POST_RECEIVE" "$@"
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
