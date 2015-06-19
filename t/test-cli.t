#!/bin/sh

d=$(dirname "$0")
cd "$d" || exit 1
. ./helper-functions.sh || exit 1
test_description="Command-line interface"
. ./sharness.sh || exit 1
D=$SHARNESS_TEST_DIRECTORY

git_multimail=$D/../git-multimail/git_multimail.py

test_expect_success '--help' '
	$git_multimail --help >actual &&
	grep -e ^Usage: -e ^Options: actual
'

test_expect_success '-v, --version' '
	$git_multimail --version >actual &&
	$git_multimail -v >actual-short &&
	test_cmp actual actual-short &&
	grep "^git-multimail version" actual
'

test_done
