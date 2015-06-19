#!/bin/sh

d=$(dirname "$0")
cd "$d" || exit 1
. ./helper-functions.sh || exit 1
test_description="Python unit-tests"
. ./sharness.sh || exit 1
D=$SHARNESS_TEST_DIRECTORY

test_expect_success "test-env" '
    "$D"/test-env
'

test_done
