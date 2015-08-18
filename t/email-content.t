#!/bin/sh

d=$(dirname "$0")
cd "$d" || exit 1
test_description="Test email content"
. ./sharness.sh || exit 1
. "$SHARNESS_TEST_DIRECTORY"/helper-functions.sh || exit 1
D=$SHARNESS_TEST_DIRECTORY

test_expect_success 'Setup test repo' '
	TESTREPO=$("$D/create-test-repo")

	cd "$TESTREPO"
'

MULTIMAIL_VERSION_QUOTED=$("$MULTIMAIL" --version |
    sed -e 's/^git-multimail version //' -e 's@[/\\]@\\\0@g')
export MULTIMAIL_VERSION_QUOTED

test_email_content() {
	log "Comparing generated emails to $d/multimail.expect ..."

	"$SHARNESS_TEST_DIRECTORY"/generate-test-emails 2>&1 |
	"$SHARNESS_TEST_DIRECTORY"/filter-noise >/tmp/multimail.actual

	GIT_PAGER=cat git diff -u "$SHARNESS_TEST_DIRECTORY"/multimail.expect /tmp/multimail.actual
	if test $? -ne 0
	then
		fatal "
===========================================================================
FAILURE!
Please investigate the discrepancies shown above.
If you are sure that your version is correct, then please

    cp /tmp/multimail.actual $d/multimail.expect

and commit."
	fi
}

test_expect_success "test-email-content" '
	test_email_content
'

test_done
