#!/bin/sh

test_description="Test email content"
. ./sharness.sh || exit 1
. "$SHARNESS_TEST_DIRECTORY"/helper-functions.sh || exit 1

test_expect_success 'Setup test repo' '
	TESTREPO=$("$SHARNESS_TEST_DIRECTORY/create-test-repo") &&

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

test_email_content() {
	prereq=
	setup_cmd=
	if test $# -ge 4
	then
		prereq=$1
		shift
	fi
	if test $# -ge 4
	then
		setup_cmd="
		$1 &&"
		shift
	fi
	test_name=$1
	file=$2
	test_content=$3
	test_expect_success $prereq "$test_name" "
	log 'Generating emails to file $file ...' && $setup_cmd
	if ( $test_content	) >$file 2>&1
	then
		echo 'Email content generated successfully.'
	else
		echo 'Error while generating email content:' &&
		cat $file &&
		false
	fi &&
	check_email_content $file email-content.d/$file
	"
}

test_email_content 'Create a ref' create-master '
	test_create refs/heads/master
'

test_email_content 'HTML messages' html '
	test_update refs/heads/master refs/heads/master^^ -c multimailhook.commitEmailFormat=html
'

test_email_content 'tag create/update/delete' simple-tag '
	test_create refs/tags/tag &&
	test_update refs/tags/tag refs/heads/master &&
	test_delete refs/tags/tag
'

test_email_content 'annotated tag create/update/delete' annotated-tag '
	test_create refs/tags/tag-annotated &&
	test_update refs/tags/tag-annotated refs/heads/master &&
	test_delete refs/tags/tag-annotated
'

test_email_content 'annotated tag create/update/delete (new content)' \
    annotated-tag-content '
	test_create refs/tags/tag-annotated-new-content &&
	test_update refs/tags/tag-annotated-new-content refs/heads/master &&
	test_delete refs/tags/tag-annotated-new-content
'

test_email_content 'annotated tag create/update/delete (tag to tree and recursive)' \
    annotated-tag-tree '
	test_create refs/tags/tree-tag &&
	test_update refs/tags/tree-tag refs/heads/master &&
	test_delete refs/tags/tree-tag &&
	test_create refs/tags/recursive-tag &&
	test_update refs/tags/recursive-tag refs/heads/master &&
	test_delete refs/tags/recursive-tag
'

test_email_content 'refFilter inclusion/exclusion/doSend/DontSend' ref-filter '
	echo "** Expected below: error" &&
	verbose_do test_must_fail test_update refs/heads/master refs/heads/master^^ -c multimailhook.refFilterExclusionRegex=^refs/heads/master$ -c multimailhook.refFilterInclusionRegex=whatever &&
	echo "** Expected below: no output" &&
	verbose_do test_update refs/heads/master refs/heads/master^^ -c multimailhook.refFilterExclusionRegex=^refs/heads/master$ &&

	verbose_do test_update refs/heads/master refs/heads/master^^ \
		-c multimailhook.refFilterExclusionRegex=^refs/heads/foo$ \
		-c multimailhook.refFilterExclusionRegex=^refs/heads/master$ \
		-c multimailhook.refFilterExclusionRegex=^refs/heads/bar$ &&

	verbose_do test_update refs/heads/master refs/heads/master^^ \
		-c multimailhook.refFilterExclusionRegex="^refs/heads/foo$ ^refs/heads/master$ ^refs/heads/bar$" \

	verbose_do test_update refs/heads/master refs/heads/master^^ -c multimailhook.refFilterInclusionRegex=^refs/heads/feature$ &&

	echo "** Expected below: no output, we should match a substring anywhere in the ref" &&
	verbose_do test_update refs/heads/master refs/heads/master^^ -c multimailhook.refFilterExclusionRegex=master$ &&

	echo "** Expected below: a refchange email with all commits marked as new" &&
	verbose_do test_update refs/heads/master refs/heads/master^^ -c multimailhook.refFilterInclusionRegex=^refs/heads/master$ &&

	echo "** Expected below: a refchange email with m1 and a5 marked as new and others as add" &&
	verbose_do test_update refs/heads/master refs/heads/master^^ -c multimailhook.refFilterDoSendRegex=^refs/heads/master$
'

# Accents seem to be accepted everywhere except in the email part
# (sébastien@example.com).
test_expect_success 'Non-ascii characters in email (setup)' '
	git checkout --detach master &&
	echo "Contenu accentué" >fichier-accentué.txt &&
	git add fichier-accentué.txt &&
	git commit -m "Message accentué" --author="Sébastien <sebastien@example.com>"
'

test_email_content '' 'test_when_finished "git checkout master"' \
    'Non-ascii characters in email (test)' accent '
	test_update HEAD HEAD^ -c multimailhook.from=author
'

test_email_content 'Gerrit environment' gerrit '
	# (no verbose_do since "$MULTIMAIL" changes from a machine to another)
	echo \$ git_multimail.py --stdout --oldrev refs/heads/master^ --newrev refs/heads/master --refname master --project démo-project --submitter "Sûb Mitter (sub.mitter@example.com)" &&
	  "$PYTHON" "$MULTIMAIL" --stdout --oldrev refs/heads/master^ --newrev refs/heads/master --refname master --project démo-project --submitter "Sûb Mitter (sub.mitter@example.com)" >out &&
	RETCODE=$? &&
	cat out &&
	test $RETCODE = 0 &&
	echo \$ git_multimail.py --stdout --oldrev refs/heads/master^ --newrev refs/heads/master --refname master --project demo-project --submitter "Submitter without Email" &&
	  "$PYTHON" "$MULTIMAIL" --stdout --oldrev refs/heads/master^ --newrev refs/heads/master --refname master --project demo-project --submitter "Submitter without Email" >out &&
	RETCODE=$? &&
	cat out &&
	test $RETCODE = 0
'

# The old test infrastructure was using one big 'generate-test-emails'
# script. Existing tests are kept there, but new tests should be added
# with separate test_expect_success.
test_email_content '' save_git_config 'Tests in generate-test-emails' all '
	. "$SHARNESS_TEST_DIRECTORY"/generate-test-emails
'

# We don't yet handle accents in the address part.
test_expect_failure 'Non-ascii characters in email (address part)' '
	git checkout --detach master &&
	test_when_finished "git checkout master" &&
	echo "Contenu accentué" >fichier-accentué.txt &&
	git add fichier-accentué.txt &&
	git commit -m "Message accentué" --author="Sébastien <sébastien@example.com>" &&
	log "Generating emails ..." &&
	if ! ( test_update HEAD HEAD^ -c multimailhook.from=author ) >accent 2>&1
	then
		log "Email generation failed:" &&
		cat accent &&
		false
	fi
'

test_expect_failure 'Non-ascii characters in email (address part): content check' '
	check_email_content accent-address email-content.d/accent-address
'

test_done
