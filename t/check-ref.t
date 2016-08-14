#!/bin/sh

test_description="Test --check-filter"
. ./sharness.sh || exit 1
. "$SHARNESS_TEST_DIRECTORY"/helper-functions.sh || exit 1

test_expect_success 'Setup test repo' '
	TESTREPO=$("$SHARNESS_TEST_DIRECTORY/create-test-repo") &&

	cd "$TESTREPO"
'

test_expect_success '--check-ref-filter with no filter' "
	$MULTIMAIL --check-ref-filter >actual &&
	cat <<-\EOF >expect &&
DoSend/DontSend filter regex (inclusion): .*
Include/Exclude filter regex (exclusion): ^refs/notes/

Refs marked as EXCLUDE are excluded by either refFilterInclusionRegex
or refFilterExclusionRegex. No emails will be sent for commits included
in these refs.
Refs marked as DONT-SEND are excluded by either refFilterDoSendRegex or
refFilterDontSendRegex, but not by either refFilterInclusionRegex or
refFilterExclusionRegex. Emails will be sent for commits included in these
refs only when the commit reaches a ref which isn't excluded.
Refs marked as DO-SEND are not excluded by any filter. Emails will
be sent normally for commits included in these refs.

refs/foo/bar DO-SEND
refs/heads/feature DO-SEND
refs/heads/foo DO-SEND
refs/heads/formatting DO-SEND
refs/heads/master DO-SEND
refs/heads/release DO-SEND
refs/remotes/remote DO-SEND
refs/tags/recursive-tag DO-SEND
refs/tags/tag DO-SEND
refs/tags/tag-annotated DO-SEND
refs/tags/tag-annotated-new-content DO-SEND
refs/tags/tree DO-SEND
refs/tags/tree-tag DO-SEND
EOF
	test_cmp actual expect
"

test_expect_success '--check-ref-filter with exclude filter' "
	$MULTIMAIL -c multimailhook.refFilterExclusionRegex=release --check-ref-filter >actual &&
	cat <<-\EOF >expect &&
DoSend/DontSend filter regex (inclusion): .*
Include/Exclude filter regex (exclusion): release|^refs/notes/

Refs marked as EXCLUDE are excluded by either refFilterInclusionRegex
or refFilterExclusionRegex. No emails will be sent for commits included
in these refs.
Refs marked as DONT-SEND are excluded by either refFilterDoSendRegex or
refFilterDontSendRegex, but not by either refFilterInclusionRegex or
refFilterExclusionRegex. Emails will be sent for commits included in these
refs only when the commit reaches a ref which isn't excluded.
Refs marked as DO-SEND are not excluded by any filter. Emails will
be sent normally for commits included in these refs.

refs/foo/bar DO-SEND
refs/heads/feature DO-SEND
refs/heads/foo DO-SEND
refs/heads/formatting DO-SEND
refs/heads/master DO-SEND
refs/heads/release EXCLUDE
refs/remotes/remote DO-SEND
refs/tags/recursive-tag DO-SEND
refs/tags/tag DO-SEND
refs/tags/tag-annotated DO-SEND
refs/tags/tag-annotated-new-content DO-SEND
refs/tags/tree DO-SEND
refs/tags/tree-tag DO-SEND
EOF
	test_cmp actual expect
"

test_expect_success '--check-ref-filter with dosend filter' "
	$MULTIMAIL -c multimailhook.refFilterDoSendRegex=annotated --check-ref-filter >actual &&
	cat <<-\EOF >expect &&
DoSend/DontSend filter regex (inclusion): annotated
Include/Exclude filter regex (exclusion): ^refs/notes/

Refs marked as EXCLUDE are excluded by either refFilterInclusionRegex
or refFilterExclusionRegex. No emails will be sent for commits included
in these refs.
Refs marked as DONT-SEND are excluded by either refFilterDoSendRegex or
refFilterDontSendRegex, but not by either refFilterInclusionRegex or
refFilterExclusionRegex. Emails will be sent for commits included in these
refs only when the commit reaches a ref which isn't excluded.
Refs marked as DO-SEND are not excluded by any filter. Emails will
be sent normally for commits included in these refs.

refs/foo/bar DONT-SEND
refs/heads/feature DONT-SEND
refs/heads/foo DONT-SEND
refs/heads/formatting DONT-SEND
refs/heads/master DONT-SEND
refs/heads/release DONT-SEND
refs/remotes/remote DONT-SEND
refs/tags/recursive-tag DONT-SEND
refs/tags/tag DONT-SEND
refs/tags/tag-annotated DO-SEND
refs/tags/tag-annotated-new-content DO-SEND
refs/tags/tree DONT-SEND
refs/tags/tree-tag DONT-SEND
EOF
	test_cmp actual expect
"

test_expect_success '--check-ref-filter with both filters' "
	$MULTIMAIL -c multimailhook.refFilterExclusionRegex=/f -c multimailhook.refFilterDontSendRegex=^refs/heads --check-ref-filter >actual &&
	cat <<-\EOF >expect &&
DoSend/DontSend filter regex (exclusion): ^refs/heads
Include/Exclude filter regex (exclusion): /f|^refs/notes/

Refs marked as EXCLUDE are excluded by either refFilterInclusionRegex
or refFilterExclusionRegex. No emails will be sent for commits included
in these refs.
Refs marked as DONT-SEND are excluded by either refFilterDoSendRegex or
refFilterDontSendRegex, but not by either refFilterInclusionRegex or
refFilterExclusionRegex. Emails will be sent for commits included in these
refs only when the commit reaches a ref which isn't excluded.
Refs marked as DO-SEND are not excluded by any filter. Emails will
be sent normally for commits included in these refs.

refs/foo/bar EXCLUDE
refs/heads/feature EXCLUDE
refs/heads/foo EXCLUDE
refs/heads/formatting EXCLUDE
refs/heads/master DONT-SEND
refs/heads/release DONT-SEND
refs/remotes/remote DO-SEND
refs/tags/recursive-tag DO-SEND
refs/tags/tag DO-SEND
refs/tags/tag-annotated DO-SEND
refs/tags/tag-annotated-new-content DO-SEND
refs/tags/tree DO-SEND
refs/tags/tree-tag DO-SEND
EOF
	test_cmp actual expect
"

test_done
