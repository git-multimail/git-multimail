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

check_email_content() {
	log "Comparing generated emails to $SHARNESS_TEST_DIRECTORY/$2 ..."

	"$SHARNESS_TEST_DIRECTORY"/filter-noise <"$1" >"$1".filtered
	GIT_PAGER=cat git diff -u "$SHARNESS_TEST_DIRECTORY/$2" "$PWD/$1".filtered
	if test $? -ne 0
	then
		error "
===========================================================================
FAILURE!
Please investigate the discrepancies shown above.
If you are sure that your version is correct, then please

    cp '$PWD/$1.filtered' '$SHARNESS_TEST_DIRECTORY/$2'

and commit."
		false
	fi
}

test_expect_success 'Create a ref' '
	log "Generating emails ..." &&
	(
		test_create refs/heads/master
	) >create-master 2>&1 &&
	check_email_content create-master email-content.d/create-master
'

test_expect_success 'HTML messages' '
	log "Generating emails ..." &&
	(
		test_update refs/heads/master refs/heads/master^^ -c multimailhook.commitEmailFormat=html
	) >html 2>&1 &&
	check_email_content html email-content.d/html
'

test_expect_success 'tag create/update/delete' '
	log "Generating emails ..." &&
	(
		test_create refs/tags/tag &&
		test_update refs/tags/tag refs/heads/master &&
		test_delete refs/tags/tag
	) >simple-tag 2>&1 &&
	check_email_content simple-tag email-content.d/simple-tag
'

# Accents seem to be accepted everywhere except in the email part
# (sébastien@example.com).
test_expect_failure 'Non-ascii characters in email' '
	git checkout --detach master &&
	test_when_finished "git checkout master" &&
	echo "Contenu accentué" >fichier-accentué.txt &&
	git add fichier-accentué.txt &&
	git commit -m "Message accentué" --author="Sébastien <sébastien@example.com>" &&
	log "Generating emails ..." &&
	(
		test_update HEAD HEAD^ -c multimailhook.from=author
	) >accent 2>&1 &&
	check_email_content accent email-content.d/accent
'

# The old test infrastructure was using one big 'generate-test-emails'
# script. Existing tests are kept there, but new tests should be added
# with separate test_expect_success.
test_expect_success "test-email-content" '
	log "Generating emails ..."
	(
		. "$SHARNESS_TEST_DIRECTORY"/generate-test-emails
	) >all 2>&1 &&
	check_email_content all email-content.d/all
'

test_expect_success 'cleanup' '
	rm -rf "$TESTREPO"
'

test_done
