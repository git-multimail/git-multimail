#!/bin/sh

test_description="Quick sanity checks"
. ./sharness.sh || exit 1
. "$SHARNESS_TEST_DIRECTORY"/helper-functions.sh || exit 1
D=$SHARNESS_TEST_DIRECTORY

for c in \
    "$PYTHON" \
    pep8 \
    git \
    rstcheck \
    ;
do
    unset "${c}"_installed
    ver=unavailable
    if command -v "${c}" >/dev/null 2>&1
    then
	ver=$("${c}" --version 2>&1)
	ver=${ver##* }
	test_set_prereq "$c"
    fi
    log "# $c version: $ver"
done

log "#"

test_expect_success git "sign-off" '
    "$D"/check-sign-off
'

rstcheck_file () {
    f=$1
    test_expect_success rstcheck "rstcheck $f" '
	status=0 &&
	rstcheck "$D"/../"$f" >rstcheck.out 2>&1 || status=$? &&
	cat rstcheck.out &&
	! test -s rstcheck.out &&
	return $status
    '
}
rstcheck_file README.rst
rstcheck_file CONTRIBUTING.rst
rstcheck_file doc/gitolite.rst
rstcheck_file doc/gerrit.rst
rstcheck_file t/README.rst

# E402: module level import not at top of file => we need this in the
# tests.
#
# E501: line too long (... characters) => we don't have _very_ long
# lines, but we could get better.
#
# E123: closing bracket does not match indentation of opening bracket's line
# => not raised on all pep8 version, and really constraining. We can
# probably keep ignoring it forever.
pep8_file () {
    f=$1
    test_expect_success pep8 "pep8 $f" '
	pep8 "$D"/../"$f" --ignore=E402,E501,E123
    '
}
pep8_file git-multimail/git_multimail.py
pep8_file t/test-env

test_expect_success 'Simple but verbose git-multimail run' '
	if "$MULTIMAIL" --stdout \
		HEAD HEAD^ HEAD \
		 --recipient=recipient@example.com >out 2>err
	then
		echo "Command ran OK, now checking stderr"
	else
		echo "Error running $MULTIMAIL, output below:" &&
		cat out && cat err && false
	fi &&
	cat <<-\EOF >expect-err &&
	*** Push-update of strange reference '\''HEAD'\''
	***  - incomplete email generated.
	Sending notification emails to: recipient@example.com
	EOF
	test_cmp err expect-err &&
	echo "stderr OK, now checking stdout" &&
	grep "^To: recipient@example.com" out &&
	echo "Everything all right."
'

# Test that each documented variable appears at least once outside
# comments in the testsuite. It does not give real coverage garantee,
# and we have known untested variables in untested-variables.txt, but
# this should ensure that new variables get a test.
test_expect_success 'Tests for each configuration variable' '
	variables=$(grep "^multimailhook." $D/../git-multimail/README |
		sed "s/multimailhook\.//") &&
	(
	cd "$D" &&
	status=0 &&
	for v in $variables; do
		if ! git grep -i "^[^#]*$v" >/dev/null
		then
			echo "No occurence of documented variable $v in testsuite" &&
			status=1
		fi
	done
	return $status
	)
'

test_done
