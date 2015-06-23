#!/bin/sh

d=$(dirname "$0")
cd "$d" || exit 1
. ./helper-functions.sh || exit 1
test_description="Test email content"
. ./sharness.sh || exit 1
D=$SHARNESS_TEST_DIRECTORY

test_expect_success "test-email-content" '
    "$D"/test-email-content
'

test_done
