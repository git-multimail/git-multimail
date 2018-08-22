#!/bin/sh

test_description="Command-line interface"
. ./sharness.sh || exit 1
. "$SHARNESS_TEST_DIRECTORY"/helper-functions.sh || exit 1

options='--stdout --recipients recipient@example.com'

test_expect_success '--help' '
	$MULTIMAIL --help >actual &&
	grep -e ^Usage: -e ^[Oo]ptions: actual
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
	grep "add .* three" out &&
	grep "add .* two" out &&
	test $(grep -c Subject out) -eq 1 &&
	$MULTIMAIL --force-send $options refs/heads/master master^^ master >out &&
	grep "new .* three" out &&
	grep "new .* two" out &&
	test $(grep -c Subject out) -eq 3
'

test_expect_success 'error if no recipient is configured' '
	test_must_fail $MULTIMAIL --stdout refs/heads/master master^^ master 2>err &&
	grep "No email recipients configured" err
'

test_expect_success 'GIT_MULTIMAIL_CHECK_SETUP' "
	echo some-text | GIT_MULTIMAIL_CHECK_SETUP=true $MULTIMAIL \
		-c multimailhook.mailingList=list@example.com \
		-c multimailhook.sendmailCommand=config-sendmail-command \
		| sed -e 's/\(    \(fqdn\|pusher\|repo_path\|thread_index\) : \).*/\1.../' \
		>actual &&
	cat <<-EOF >expected &&
	Environment values:
	    administrator : 'the administrator of this repository'
	    charset : 'utf-8'
	    emailprefix : '[test-repo-cli] '
	    fqdn : ...
	    projectdesc : 'UNNAMED PROJECT'
	    pusher : ...
	    repo_path : ...
	    repo_shortname : 'test-repo-cli'
	    thread_index : ...

	Now, checking that git-multimail's standard input is properly set ...
	Please type some text and then press Return
	You have just entered:
	some-text
	git-multimail seems properly set up.
	EOF
	test_cmp actual expected
"

test_done
