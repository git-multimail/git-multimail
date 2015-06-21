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
    if test $(command -v cleanup) = cleanup
    then
	cleanup
    fi
    exit 1;
}
try() { "$@" || fatal "'$@' failed"; }
