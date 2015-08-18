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
