#!/bin/sh

test_description="Test email content"
. ./sharness.sh || exit 1
. "$SHARNESS_TEST_DIRECTORY"/helper-functions.sh || exit 1

test_expect_success 'Setup test repo' '
	TESTREPO=$("$SHARNESS_TEST_DIRECTORY/create-test-repo") &&

	cd "$TESTREPO"
'

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
	if test -z "$test_expect_x"
	then
	    test_expect_x=test_expect_success
	fi
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
	$test_expect_x $prereq "$test_name" "
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

test_email_content 'To/From/Reply-to headers' headers '
	test_update refs/heads/master refs/heads/master^^ \
		-c multimailhook.mailingList=mailing-list-config@example.com \
		-c multimailhook.replyTo=reply-to-config@example.com \
		-c multimailhook.from=from-config@example.com --show-env 2>&1 |
	sed "s/\(repo_path\|fqdn\) : .*/\1 : '"'"'...'"'"'/"
'

test_email_content 'To/From/Reply-to headers' headers-specific '
	test_update refs/heads/master refs/heads/master^^ \
		-c multimailhook.mailingList=mailing-list-config@example.com \
		-c multimailhook.refChangeList=refchange-list-config@example.com \
		-c multimailhook.commitList=commit-list-config@example.com \
		-c multimailhook.replyToCommit=reply-to-commit@example.com \
		-c multimailhook.replyToRefChange=reply-to-refchange@example.com \
		-c multimailhook.fromRefChange=from-refchange@example.com \
		-c multimailhook.fromCommit=from-commit@example.com \
		-c multimailhook.from=from-config@example.com
'

test_email_content 'excludeMergeRevisions' ignoremerges '
	MULTIMAIL=$SHARNESS_TEST_DIRECTORY/test_templates.py &&
	test_update refs/heads/master refs/heads/master^^ \
		-c multimailhook.excludeMergeRevisions=true
'

test_email_content 'emailPrefix' emailprefix '
	verbose_do test_update refs/heads/master refs/heads/master^^ \
		-c multimailhook.emailPrefix="XXX{%(repo_shortname)s}YYY<%(repo_shortname)s>ZZZ" &&
	test_must_fail verbose_do test_update refs/heads/master refs/heads/master^^ \
		-c multimailhook.emailPrefix="XXX{%(repo_shortnam)s}YYY<%(repo_shortname)s>ZZZ"
'

# Some versions of Git show an ellipsis (...). Some don't. Change
# introduced in Git in c2f1d39897 (t4013: test new output from diff
# --abbrev --raw, 2017-12-03), i.e. Git 2.16. We can remove this when
# Git >= 2.16 is deployed on all machines where the testsuite is ran.
(
export GIT_PRINT_SHA1_ELLIPSIS=yes
test_email_content 'custom diff & log' diff-log '
	test_update refs/heads/master refs/heads/master^^ \
		-c multimailhook.refChangeShowLog=true \
		-c multimailhook.logOpts="--format=short --stat" \
		-c multimailhook.commitLogOpts="-p --raw" \
		-c multimailhook.diffOpts="-p" \
'
)

test_email_content 'HTML messages' html '
	test_update refs/heads/master refs/heads/master^^ -c multimailhook.commitEmailFormat=html
'

test_email_content 'message including a URL' url '
	test_update refs/heads/master refs/heads/master^ \
		-c multimailhook.commitBrowseURL="https://github.com/git-multimail/git-multimail/commit/%(id)s" \
		-c multimailhook.commitEmailFormat=html &&
	test_update refs/heads/master refs/heads/master^ \
		-c multimailhook.commitBrowseURL="https://github.com/git-multimail/git-multimail/commit/" \
		-c multimailhook.commitEmailFormat=text &&
	test_update refs/heads/master refs/heads/master^ \
		-c multimailhook.commitBrowseURL="https://example.com/path\"with<spe\cial%%chars/%(newrev)s/this-comes-after-id" \
		-c multimailhook.commitEmailFormat=html &&
	test_update refs/heads/master refs/heads/master^ \
		-c multimailhook.commitBrowseURL="https://example.com/path\"with<spe\cial\>chars/%()s" \
		-c multimailhook.commitEmailFormat=text
'

test_email_content 'combined message including a URL' combined-url '
	verbose_do git config multimailhook.refchangelist "Commit List <commitlist@example.com>"
	test_update refs/heads/master refs/heads/master^ \
		-c multimailhook.commitBrowseURL="https://example.com/path\"with<spe\cial%%chars/%(newrev)s/this-comes-after-id" \
		-c multimailhook.commitEmailFormat=html &&
	test_update refs/heads/master refs/heads/master^ \
		-c multimailhook.commitBrowseURL="https://example.com/path\"with<spe\cial\>chars/%()s" \
		-c multimailhook.commitEmailFormat=text
	verbose_do git config multimailhook.refchangelist "Refchange List <refchangelist@example.com>"
'

test_email_content 'HTML message with template override' html-templates '
	MULTIMAIL=$SHARNESS_TEST_DIRECTORY/test_templates.py &&
	verbose_do test_update refs/heads/master \
		refs/heads/master^^ -c multimailhook.commitEmailFormat=html &&
	verbose_do test_update refs/heads/master \
		refs/heads/master^^ -c multimailhook.commitEmailFormat=html \
				    -c multimailhook.htmlInIntro=true
	verbose_do test_update refs/heads/master \
		refs/heads/master^^ -c multimailhook.commitEmailFormat=html \
				    -c multimailhook.htmlInIntro=true \
				    -c multimailhook.htmlInFooter=true
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

test_email_content 'restrict email count and size' max '
	verbose_do test_update refs/heads/master foo \
		-c multimailhook.refFilterDontSendRegex=^refs/heads/feature$ \
		-c multimailhook.maxCommitEmails=4 &&
	verbose_do test_update refs/heads/master foo \
		-c multimailhook.refFilterDontSendRegex=^refs/heads/feature$ \
		-c multimailhook.emailMaxLines=10 \
		-c multimailhook.emailMaxLineLength=15 &&
	verbose_do test_update refs/heads/formatting formatting^^ \
		-c multimailhook.emailMaxLines=1 \
		-c multimailhook.emailMaxLineLength=15 &&
	verbose_do test_update refs/heads/formatting formatting^^ \
		-c multimailhook.emailMaxLines=1 \
		-c multimailhook.emailMaxLineLength=15 \
		-c multimailhook.subjectMaxLength=20 &&
	verbose_do test_update refs/heads/formatting formatting^^ \
		-c multimailhook.emailMaxLines=0 \
		-c multimailhook.emailMaxLineLength=0 \
		-c multimailhook.subjectMaxLength=0
'

test_email_content 'refFilter inclusion/exclusion/doSend/DontSend' ref-filter '
	echo "** Expected below: error" &&
	verbose_do test_must_fail test_update refs/heads/master refs/heads/master^^ -c multimailhook.refFilterExclusionRegex=^refs/heads/master$ -c multimailhook.refFilterInclusionRegex=whatever &&
	echo "** Expected below: error" &&
	verbose_do test_must_fail test_update refs/heads/master refs/heads/master^^ -c multimailhook.refFilterDontSendRegex=^refs/heads/master$ -c multimailhook.refFilterDoSendRegex=whatever &&
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
	verbose_do test_update refs/heads/master refs/heads/master^^ -c multimailhook.refFilterDoSendRegex=^refs/heads/master$ &&

	echo "** Expected below: a refchange email with f1, f2, f3 marked as add and others as new" &&
	echo "   (f1, f2, f3 were made on a DontSend feature branch, hence completely excluded)" &&
	verbose_do test_update refs/heads/master foo -c multimailhook.refFilterDontSendRegex=^refs/heads/feature$

	echo "** Expected below: nothing, the branch is marked as dontSend" &&
	verbose_do test_update refs/heads/master foo -c multimailhook.refFilterDontSendRegex=^refs/heads/master$

	echo "** Expected below: nothing, the branch is not marked as doSend" &&
	verbose_do test_update refs/heads/master foo -c multimailhook.refFilterDoSendRegex=^refs/heads/feature$

	echo "** Expected below: a refchange email with all marked as new" &&
	echo "   (ExclusionRegex just ignores pushes to feature, but not commits made on feature)" &&
	verbose_do test_update refs/heads/master foo -c multimailhook.refFilterExclusionRegex=^refs/heads/feature$
'

# Accents seem to be accepted everywhere except in the email part
# (sébastien@example.com).
test_expect_success 'Non-ascii characters in email (setup)' '
	git checkout --detach master &&
	( echo "Contenu accentué\né\n1é234567890\n12é34567890\n123é4567890"
	  printf "Non-UTF-8\n\3511234567890\n1\351234567890\n12\35134567890\n123\3514567890\n" ) \
	   >fichier-accentué.txt &&
	git add fichier-accentué.txt &&
	git commit -m "Message accentué" --author="Sébastien <sebastien@example.com>"
'

# In Python 3, we manipulate everything as UTF-8 internally, hence we
# can't really deal with emailStrictUTF8=false
test_email_content '' 'test_when_finished "git checkout master && git branch -D mâstér"' \
    'Non-ascii characters in email (test)' accent-python$PYTHON_VERSION '
	git checkout -b mâstér &&
	verbose_do test_update refs/heads/mâstér refs/heads/mâstér^ \
		 -c multimailhook.from=author &&
	verbose_do test_update refs/heads/mâstér refs/heads/mâstér^ \
		-c multimailhook.from=author \
		-c multimailhook.emailMaxLineLength=10 \
		-c multimailhook.subjectMaxLength=0 &&
	verbose_do test_update refs/heads/mâstér refs/heads/mâstér^ \
		-c multimailhook.from=author \
		-c multimailhook.emailMaxLineLength=10 \
		-c multimailhook.subjectMaxLength=0 \
		-c multimailhook.emailStrictUTF8=false
'

test_email_content 'Push to HEAD' head '
	test_update HEAD HEAD^
'

test_email_content 'Gerrit environment' gerrit '
	# (no verbose_do since "$MULTIMAIL" changes from a machine to another)
	test_when_finished "git checkout -b master && git branch -d mastèr" &&
	git checkout -b mastèr && git branch -d master &&
	echo \$ git_multimail.py --stdout --oldrev refs/heads/mastèr^ --newrev refs/heads/mastèr --refname mastèr --project démo-project --submitter "Sûb Mitter (sub.mitter@example.com)" &&
	{ "$PYTHON" "$MULTIMAIL" --stdout --oldrev refs/heads/mastèr^ --newrev refs/heads/mastèr --refname mastèr --project démo-project --submitter "Sûb Mitter (sub.mitter@example.com)" >out ; RETCODE=$? ; } &&
	cat out &&
	test $RETCODE = 0 &&
	git checkout -b master && git branch -d mastèr &&
	echo \$ git_multimail.py -c multimailhook.from= -c multimailhook.reponame= --stdout --oldrev refs/heads/master^ --newrev refs/heads/master --refname master --project demo-project --submitter "Sub Mîtter (sub.mitter@example.com)" &&
	{ "$PYTHON" "$MULTIMAIL" -c multimailhook.from= -c multimailhook.reponame= --stdout --oldrev refs/heads/master^ --newrev refs/heads/master --refname master --project demo-project --submitter "Sub Mîtter (sub.mitter@example.com)" >out ; RETCODE=$? ; } &&
	RETCODE=$? &&
	cat out &&
	test $RETCODE = 0 &&
	echo \$ git_multimail.py -c multimailhook.from= --stdout --oldrev refs/heads/master^ --newrev refs/heads/master --refname master --project demo-project --submitter "Submitter without Email" &&
	{ "$PYTHON" "$MULTIMAIL" -c multimailhook.from= --stdout --oldrev refs/heads/master^ --newrev refs/heads/master --refname master --project demo-project --submitter "Submitter without Email" >out ; RETCODE=$? ; } &&
	RETCODE=$? &&
	cat out &&
	test $RETCODE = 0
'

test_email_content 'Stash environment' stash '
	# (no verbose_do since "$MULTIMAIL" changes from a machine to another)
	echo \$ git_multimail.py --stdout refs/heads/master refs/heads/master^ refs/heads/master --stash-repo démo-project --stash-user "Stash Sûb Mitter <sub.mitter@example.com>" &&
	{ "$PYTHON" "$MULTIMAIL" --stdout refs/heads/master refs/heads/master^ refs/heads/master --stash-repo démo-project --stash-user "Stash Sûb Mitter <sub.mitter@example.com>" >out ; RETCODE=$? ; } &&
	cat out &&
	test $RETCODE = 0 &&
	echo \$ git_multimail.py -c multimailhook.from= -c multimailhook.reponame= --stdout refs/heads/master refs/heads/master^ refs/heads/master --stash-repo stash-démo-project --stash-user "Stash Sub Mîtter <sub.mitter@example.com>" &&
	{ "$PYTHON" "$MULTIMAIL" -c multimailhook.from= -c multimailhook.reponame= --stdout refs/heads/master refs/heads/master^ refs/heads/master --stash-repo stash-démo-project --stash-user "Stash Sub Mîtter <sub.mitter@example.com>" >out ; RETCODE=$? ; } &&
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
