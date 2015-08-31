#!/bin/sh

test_description="Python unit-tests"
. ./sharness.sh || exit 1
. "$SHARNESS_TEST_DIRECTORY"/helper-functions.sh || exit 1

test_expect_success "test-env" '
    "$PYTHON" "$SHARNESS_TEST_DIRECTORY"/test-env
'

test_done
