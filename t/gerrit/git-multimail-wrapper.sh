#! /bin/sh

die () {
	echo "$*"
	exit 1
}

dir=$(dirname "$0")

(
	date
	printf '%s' "$0"
	printf ' "%s"' "$@"
	echo
	"$dir"/../../git-multimail/git_multimail.py --stdout "$@"
	echo
) >> /tmp/git-multimail-wrapper-log.txt 2>&1
