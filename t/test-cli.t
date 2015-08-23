#!/bin/sh

d=$(dirname "$0")
cd "$d" || exit 1
test_description="Command-line interface"
. ./sharness.sh || exit 1
. "$SHARNESS_TEST_DIRECTORY"/helper-functions.sh || exit 1
D=$SHARNESS_TEST_DIRECTORY

options='--stdout --recipients recipient@example.com'

test_expect_success '--help' '
	$MULTIMAIL --help >actual &&
	grep -e ^Usage: -e ^Options: actual
'

test_expect_success '-v, --version' '
	$MULTIMAIL --version >actual &&
	$MULTIMAIL -v >actual-short &&
	test_cmp actual actual-short &&
	grep "^git-multimail version" actual
'

test_expect_success 'setup test repo' '
	git init test-repo-cli.git &&
	cd test-repo-cli.git &&
	GIT_AUTHOR_DATE="100000000 +0200" &&
	GIT_COMMITTER_DATE="100000010 +0200" &&
	GIT_AUTHOR_NAME="Auth Or" &&
	GIT_AUTHOR_EMAIL="Auth.Or@example.com" &&
	GIT_COMMITTER_NAME="Comm Itter" &&
	GIT_COMMITTER_EMAIL="Comm.Itter@example.com" &&
	export GIT_AUTHOR_DATE GIT_COMMITTER_DATE GIT_AUTHOR_NAME \
	    GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL &&
	echo one   >file && git add . && git commit -m one &&
	echo two   >file && git commit -am two &&
	echo three >file && git commit -am three &&
	git checkout -b branch HEAD^ &&
	echo 3 >file && git commit -am 3 &&
	echo 4 >file && git commit -am 4 &&
	! git merge master &&
	echo merge >file && git commit -am merge &&
	git log --oneline --decorate --graph
'

test_expect_success '--force-send does consider everything new' '
	$MULTIMAIL $options refs/heads/master master^^ master >out &&
	grep "adds .* three" out &&
	grep "adds .* two" out &&
	test $(grep -c Subject out) -eq 1 &&
	$MULTIMAIL --force-send $options refs/heads/master master^^ master >out &&
	grep "new .* three" out &&
	grep "new .* two" out &&
	test $(grep -c Subject out) -eq 3
'

test_done
