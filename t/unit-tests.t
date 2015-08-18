#!/bin/sh

d=$(dirname "$0")
cd "$d" || exit 1
test_description="Python unit-tests"
. ./sharness.sh || exit 1
. "$SHARNESS_TEST_DIRECTORY"/helper-functions.sh || exit 1

test_expect_success PYTHON2 "test-env" '
    "$PYTHON" "$SHARNESS_TEST_DIRECTORY"/test-env
'

test_expect_success PYTHON3 "test-env3" '
    cp "$SHARNESS_TEST_DIRECTORY"/test-env "$SHARNESS_TEST_DIRECTORY"/test-env3 &&
    2to3 -w "$SHARNESS_TEST_DIRECTORY"/test-env3 &&
    perl -pi -e "s/git_multimail/git_multimail3/" "$SHARNESS_TEST_DIRECTORY"/test-env3 &&
    "$PYTHON" "$SHARNESS_TEST_DIRECTORY"/test-env3
'

test_done
